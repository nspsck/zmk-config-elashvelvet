#!/usr/bin/env python3
"""Check the Corne port against its source, without a Zephyr toolchain.

Usage: python3 scripts/check_keymap.py [--corne ../zmk-new_corne/config/eyelash_corne.keymap]
This validates mapping and behavior preservation; it does not compile firmware.
"""

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def clean(text):
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)


def block(text, marker):
    start = re.search(marker + r"\s*\{", text)
    assert start, f"Missing node: {marker}"
    offset = start.end()
    depth = 1
    for end in range(offset, len(text)):
        depth += (text[end] == "{") - (text[end] == "}")
        if depth == 0:
            return text[offset:end]
    raise AssertionError(f"Unclosed node: {marker}")


def cells(text, property_name):
    match = re.search(r"\b" + property_name + r"\s*=\s*<(.*?)>;", text, re.S)
    assert match, f"Missing property: {property_name}"
    return match.group(1)


def layers(text):
    result = []
    keymap = block(text, r"\bkeymap")
    for match in re.finditer(r"\b(?:default_layer|layer_\d+)\s*\{", keymap):
        body = block(keymap[match.start():], r"(?:default_layer|layer_\d+)")
        name = re.search(r'display-name\s*=\s*"([^"]+)"', body).group(1)
        entries = [" ".join(s.split()) for s in re.split(r"(?=&)", cells(body, "bindings")) if s.strip()]
        result.append((name, entries, body))
    return result


def normalized(text):
    return " ".join(text.split())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corne", type=Path, default=ROOT.parent / "zmk-new_corne/config/eyelash_corne.keymap")
    args = parser.parse_args()
    source = clean(args.corne.read_text())
    target = clean((ROOT / "config/velvet.keymap").read_text())
    source_layers, target_layers = layers(source), layers(target)
    names = ["CMKDH", "GAMING", "SYMNUM", "FN", "MOUSE", "WM", "SCROLL", "PRECISION"]
    assert [row[0] for row in target_layers] == names, "Layer order changed"
    assert all(len(row[1]) == 61 for row in target_layers), "Every Velvet layer needs 61 positions"
    assert len(source_layers) == 6 and all(len(row[1]) == 48 for row in source_layers)

    # Physical typing rows, left then right, followed by the six primary thumbs.
    corne_positions = [*range(0, 6), *range(7, 13), *range(13, 19), *range(22, 28),
                       *range(28, 34), *range(36, 42), *range(42, 48)]
    velvet_positions = [*range(12, 18), *range(19, 25), *range(25, 31), *range(32, 38),
                        *range(38, 44), *range(45, 51), *range(53, 59)]
    mapping = dict(zip(corne_positions, velvet_positions))
    assert len(mapping) == 42 and len(set(mapping.values())) == 42
    for index, (name, bindings, _) in enumerate(source_layers):
        for old, new in mapping.items():
            expected = bindings[old]
            if expected.startswith("&rgb_ug"):
                expected = "&none"
            elif expected == "&soft_off":
                expected = "&VELVET_SOFT_OFF"
            assert target_layers[index][1][new] == expected, f"{name}: Corne {old} → Velvet {new} differs"

    # Preserve the entire used hold-tap definitions, including timings and flags,
    # after translating only their positional constraints.
    for marker in [r"&mt", r"mod_kp:\s*mod_kp", r"to_kp:\s*to_kp", r"hml:\s*home_row_mod_left",
                   r"hmr:\s*home_row_mod_right", r"mt_pinky:\s*mt_pinky"]:
        old, new = block(source, marker), block(target, marker)
        def mapped_positions(match):
            return "hold-trigger-key-positions = <" + " ".join(str(mapping[int(n)]) for n in match[1].split()) + ">;"
        old = re.sub(r"hold-trigger-key-positions\s*=\s*<([^>]+)>;", mapped_positions, old)
        assert normalized(old) == normalized(new), f"Hold-tap changed: {marker}"

    for name in ["softoff", "esc", "tab", "bspc", "quote"]:
        old, new = block(source, r"\b" + name), block(target, r"\b" + name)
        old = re.sub(r"key-positions\s*=\s*<([^>]+)>;",
                     lambda m: "key-positions = <" + " ".join(str(mapping[int(n)]) for n in m[1].split()) + ">;", old)
        assert normalized(old) == normalized(new), f"Combo changed: {name}"

    for index in (0, 1):
        bindings = target_layers[index][1]
        assert [bindings[i] for i in [18, 31, 44]] == ["&mkp RCLK", "&mkp MCLK", "&mkp LCLK"]
        assert bindings[51:53] == ["&kp C_MUTE", "&kp C_PP"]
        assert bindings[59:] == ["&mo VELVET_LAYER_SCROLL", "&mo VELVET_LAYER_PRECISION"]
    assert all(binding == "&trans" for row in target_layers[6:] for binding in row[1]), "Pointer modes must preserve held keys"
    assert all(normalized(cells(row[2], "sensor-bindings")) == "&rsr_vol" for row in target_layers)
    conditional = block(target, r"\bmouse_numpad")
    assert normalized(cells(conditional, "if-layers")) == "VELVET_LAYER_SYMNUM VELVET_LAYER_FN"
    assert normalized(cells(conditional, "then-layer")) == "VELVET_LAYER_MOUSE"
    assert normalized(cells(block(target, r"\bscroller"), "layers")) == "VELVET_LAYER_SCROLL", "WM must not activate trackball scrolling"
    assert normalized(cells(block(target, r"\bprecision"), "layers")) == "VELVET_LAYER_PRECISION"
    assert "&rgb_ug" not in target and "&bl " not in target, "Unsupported RGB must not become a power control"
    for prop in ("hold-trigger-key-positions", "key-positions"):
        for match in re.finditer(prop + r"\s*=\s*<([^>]+)>;", target):
            assert all(0 <= int(value) < 61 for value in match[1].split()), f"Invalid position in {prop}"
    print("PASS: 8 × 61 bindings; all 252 Corne key mappings, 6 hold-taps, 5 combos, pointer layers, mouse buttons and encoder checked.")


if __name__ == "__main__":
    main()
