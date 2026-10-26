#!/usr/bin/env python3
"""Check editable Velvet keymaps without a Zephyr installation.

Runs the host C preprocessor for both halves, with soft-off enabled and disabled.
Local includes and conditional directives are processed normally. External ZMK
headers are explicit include-marker stubs: this checks their availability in
each branch, NOT their contents, keycode definitions, bindings, or DTS schemas.
Then checks layer lengths, position ranges, and layer references. This is a
preflight check, not a firmware build or a comparison with the original Corne.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
KEY_COUNT = 61
COMMON_HEADERS = {
    "behaviors.dtsi", "dt-bindings/zmk/keys.h", "dt-bindings/zmk/bt.h",
    "dt-bindings/zmk/pointing.h", "zephyr/dt-bindings/input/input-event-codes.h",
    "input/processors.dtsi", "behaviors/runtime-sensor-rotate.dtsi",
}
INCLUDE = re.compile(r'^[ \t]*#[ \t]*include[ \t]*([<"])([^>"\n]+)[>"]([^\n]*)', re.M)
STRINGS_AND_COMMENTS = re.compile(r'"(?:\\.|[^"\\])*"|/\*.*?\*/|//[^\n]*', re.S)
LAYER_BEHAVIORS = {"mo", "to", "tog", "sl", "lt"}
# Zephyr processes DTS before Kconfig. Only the right build explicitly passes
# VELVET_RIGHT via DTS_EXTRA_CPPFLAGS; CONFIG_SHIELD_* is not available here.
HALF_DEFINES = {"left": (), "right": ("VELVET_RIGHT",)}


class CheckError(ValueError):
    """A keymap failed a preflight check."""


@dataclass
class CheckReport:
    layers: int
    keys: int = KEY_COUNT
    variants: int = 4


def clean(text):
    """Remove comments while retaining strings and source line numbers."""
    return STRINGS_AND_COMMENTS.sub(
        lambda m: m[0] if m[0].startswith('"') else " " + "\n" * m[0].count("\n"), text)


def preprocess(keymap, defines, compiler=None):
    """Use real CPP semantics, substituting only external include contents."""
    keymap = Path(keymap).resolve()
    compiler = compiler or next((shutil.which(c) for c in ("clang", "gcc", "cc", "cpp")
                                 if shutil.which(c)), None)
    if not compiler:
        raise CheckError("No host C preprocessor found; install clang or GCC to run this check")
    with tempfile.TemporaryDirectory(prefix="velvet-keymap-check-") as directory:
        staging = Path(directory)
        local_files, external_files, markers = {}, {}, {}

        def stage(path):
            path = path.resolve()
            if path in local_files:
                return local_files[path]
            target = staging / f"local_{len(local_files)}{path.suffix}"
            local_files[path] = target
            # CPP decides whether an absent include is active: an unused
            # conditional branch may legitimately reference an absent file.
            if not path.is_file():
                return target

            def include(match):
                delimiter, name, trailing = match.groups()
                relative, root_relative = path.parent / name, keymap.parent / name
                if relative.is_file() or root_relative.is_file() or delimiter == '"':
                    candidate = relative if relative.is_file() else root_relative
                    replacement = stage(candidate)
                else:
                    if name not in external_files:
                        marker = f"__VELVET_CHECK_INCLUDE_{len(external_files)}__"
                        replacement = staging / f"external_{len(external_files)}.h"
                        replacement.write_text(marker + "\n")
                        external_files[name], markers[marker] = replacement, name
                    replacement = external_files[name]
                return f'#include "{replacement.name}"{trailing}'

            target.write_text(INCLUDE.sub(include, clean(path.read_text())))
            return target

        if not keymap.is_file():
            raise CheckError(f"Keymap not found: {keymap}")
        source = stage(keymap)
        command = [compiler, "-E", "-P", "-x", "assembler-with-cpp", "-nostdinc", "-undef",
                   "-D__DTS__=1"]
        command.extend(f"-D{name}=1" for name in defines)
        try:
            result = subprocess.run(command + [str(source)], capture_output=True, text=True,
                                    timeout=15, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CheckError(f"Cannot run host preprocessor: {error}") from error
        if result.returncode:
            diagnostic = result.stderr.strip()
            for original, temporary in local_files.items():
                diagnostic = diagnostic.replace(str(temporary), str(original))
            raise CheckError(f"Host preprocessor rejected keymap:\n{diagnostic}")
        active_headers = {name for marker, name in markers.items()
                          if re.search(r"\b" + marker + r"\b", result.stdout)}
        return re.sub(r"__VELVET_CHECK_INCLUDE_\d+__", "", result.stdout), active_headers


def matching_brace(text, opening):
    depth = 1
    for token in re.finditer(r'"(?:\\.|[^"\\])*"|[{}]', text[opening + 1:]):
        if token[0] == "{":
            depth += 1
        elif token[0] == "}":
            depth -= 1
            if depth == 0:
                return opening + 1 + token.start()
    raise CheckError("Unclosed devicetree node")


def node_body(text, name):
    match = re.search(r"(?<![-\w])" + re.escape(name) + r"\s*\{", text)
    if not match:
        raise CheckError(f"Missing {name} node")
    opening = match.end() - 1
    return text[opening + 1:matching_brace(text, opening)]


def child_nodes(text):
    """Read direct child nodes without depending on generated layer names."""
    cursor = 0
    pattern = re.compile(r"(?:([\w-]+)\s*:\s*)?([\w,@+.-]+)\s*\{")
    while match := pattern.search(text, cursor):
        opening = match.end() - 1
        closing = matching_brace(text, opening)
        yield match[1], match[2], text[opening + 1:closing]
        cursor = closing + 1


def cells(text, name):
    match = re.search(r"(?<![-\w])" + re.escape(name) + r"\s*=\s*<([^>]+)>\s*;", text, re.S)
    if not match:
        raise CheckError(f"Missing or malformed {name} property")
    return match[1]


def bindings(value):
    return [(m[1], m[2].strip()) for m in re.finditer(r"&([A-Za-z_]\w*)\b([^&]*)", value)]


def integer(value, context):
    try:
        return int(value.strip().strip("()"), 0)
    except ValueError as error:
        raise CheckError(f"Unresolved integer {value!r} in {context}") from error


def validate_structure(text):
    # Bare endif is legal assembler input, but not a directive or valid DTS.
    if re.search(r"^\s*(?:endif|else|elif\b[^\n]*)\s*$", text, re.M):
        raise CheckError("Bare conditional directive; use #endif, #else, or #elif")
    layer_nodes = list(child_nodes(node_body(text, "keymap")))
    if not layer_nodes:
        raise CheckError("Keymap has no layers")
    for _, name, body in layer_nodes:
        count = len(bindings(cells(body, "bindings")))
        if count != KEY_COUNT:
            raise CheckError(f"Layer {name} has {count} bindings; expected {KEY_COUNT}")

    def layer_id(value, context):
        number = integer(value, context)
        if not 0 <= number < len(layer_nodes):
            raise CheckError(f"Invalid layer {number} in {context}; expected 0..{len(layer_nodes) - 1}")

    for m in re.finditer(r"(?<![-\w])(hold-trigger-key-positions|key-positions)\s*=\s*<([^>]+)>;", text):
        for value in m[2].split():
            position = integer(value, m[1])
            if not 0 <= position < KEY_COUNT:
                raise CheckError(f"Invalid position {position} in {m[1]}; expected 0..{KEY_COUNT - 1}")
    for m in re.finditer(r"(?<![-\w])(if-layers|then-layer|layers)\s*=\s*<([^>]+)>;", text):
        for value in m[2].split():
            layer_id(value, m[1])

    # Follow custom hold-taps passing their first argument to a layer behavior.
    layer_behaviors = set(LAYER_BEHAVIORS)
    behavior_nodes = (list(child_nodes(node_body(text, "behaviors")))
                      if re.search(r"\bbehaviors\s*\{", text) else [])
    for _ in range(len(behavior_nodes) + 1):
        for label, _, body in behavior_nodes:
            if label and '"zmk,behavior-hold-tap"' in body:
                # Behavior definitions can contain multiple <...> groups.
                definitions = re.search(r"(?<![-\w])bindings\s*=\s*([^;]+);", body)
                linked = bindings(definitions[1]) if definitions else []
                if linked and linked[0][0] in layer_behaviors:
                    layer_behaviors.add(label)
    # References in definitions such as <&mo>, <&kp> have deferred arguments.
    for behavior, arguments in bindings(text):
        if behavior in layer_behaviors:
            first = re.match(r"\s*(\([^)]*\)|[A-Za-z_0-9+-]+)", arguments)
            if first:
                layer_id(first[1], f"&{behavior}")
    return len(layer_nodes)


def check_keymap(keymap=ROOT / "config/velvet.keymap", compiler=None):
    counts = set()
    for half, half_defines in HALF_DEFINES.items():
        for soft_off in (False, True):
            variant = f"{half.lower()}, soft-off {'on' if soft_off else 'off'}"
            defines = list(half_defines)
            if soft_off:
                defines.append("CONFIG_ZMK_PM_SOFT_OFF")
            try:
                text, headers = preprocess(keymap, defines, compiler)
                missing = COMMON_HEADERS - headers
                if missing:
                    raise CheckError("Common headers are unavailable: " + ", ".join(sorted(missing)))
                counts.add(validate_structure(text))
            except CheckError as error:
                raise CheckError(f"[{variant}] {error}") from error
    if len(counts) != 1:
        raise CheckError("Layer counts differ between half/configuration branches")
    return CheckReport(layers=counts.pop())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keymap", type=Path, default=ROOT / "config/velvet.keymap")
    args = parser.parse_args()
    try:
        report = check_keymap(args.keymap)
    except CheckError as error:
        parser.exit(1, f"FAIL: {error}\n")
    print(f"PASS: {report.layers} layers × {report.keys} bindings; position/layer references and "
          f"common includes checked in {report.variants} preprocessor variants.")
    print("External ZMK headers are stubs; this does not compile firmware or validate ZMK schemas/keycodes.")


if __name__ == "__main__":
    main()
