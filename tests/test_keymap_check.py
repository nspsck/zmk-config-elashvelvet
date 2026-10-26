"""Regressions for keymap-editor damage; no Zephyr dependencies required."""

import importlib.util
from pathlib import Path
import re
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_keymap", ROOT / "scripts/check_keymap.py")
checker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = checker
spec.loader.exec_module(checker)


class KeymapCheckTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="velvet-keymap-test-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.keymap = self.root / "velvet.keymap"
        self.headers = "\n".join(f"#include <{name}>" for name in sorted(checker.COMMON_HEADERS))
        (self.root / "layers.h").write_text("#pragma once\n#define SECOND 1\n")
        (self.root / "pointer.dtsi").write_text("""
#if defined(VELVET_RIGHT)
#include <input/processors/runtime-input-processor.dtsi>
&{/trackball_listener} { scroller { layers = <SECOND>; }; };
#endif
""")
        # Customized keys/combo and arbitrary layer names must pass without
        # depending on Corne parity or restoring the removed Corne combos.
        self.source = self.headers + """
#include "layers.h"
#include "pointer.dtsi"
/ {
    behaviors {
        custom_layer_tap: custom_layer_tap {
            compatible = "zmk,behavior-hold-tap";
            #binding-cells = <2>;
            bindings = <&mo>, <&kp>;
        };
    };
    combos {
        compatible = "zmk,combos";
        mousemiddle { bindings = <&mkp MCLK>; key-positions = <51 52>; };
    };
    keymap {
        compatible = "zmk,keymap";
        custom_typing { bindings = <BINDINGS>; };
        my_second_layer { bindings = <TRANSPARENT>; };
    };
};
"""
        self.source = self.source.replace("BINDINGS", "&kp GRAVE &custom_layer_tap SECOND SPACE " + "&kp A " * 59)
        self.source = self.source.replace("TRANSPARENT", "&trans " * 61)

    def check(self, source=None):
        self.keymap.write_text(self.source if source is None else source)
        return checker.check_keymap(self.keymap)

    def test_custom_bindings_and_middle_click_combo_pass(self):
        self.assertEqual(self.check().layers, 2)

    def test_current_repository_keymap_passes(self):
        self.assertGreater(checker.check_keymap().layers, 0)

    def test_repository_pointer_flag_matches_right_build(self):
        entries = re.split(r"(?m)^  - ", (ROOT / "build.yaml").read_text())[1:]
        right = [entry for entry in entries if "shield: velvet_right " in entry]
        self.assertEqual(len(right), 1)
        flag = "-DDTS_EXTRA_CPPFLAGS=-DVELVET_RIGHT=1"
        self.assertIn(flag, right[0])
        for entry in entries:
            if entry != right[0]:
                self.assertNotIn(flag, entry)
        keymap = ROOT / "config/velvet.keymap"
        left, _ = checker.preprocess(keymap, checker.HALF_DEFINES["left"])
        right, _ = checker.preprocess(keymap, checker.HALF_DEFINES["right"])
        self.assertNotIn("trackball_listener", left)
        self.assertIn("trackball_listener", right)

    def test_malformed_editor_endif_is_rejected(self):
        damage = "\n#if defined(CONFIG_ZMK_PM_SOFT_OFF)\n#\nendif\n"
        with self.assertRaisesRegex(checker.CheckError, "preprocessor rejected"):
            self.check(self.source.replace("    keymap {", damage + "    keymap {"))

    def test_bare_endif_is_rejected_even_with_balanced_directives(self):
        with self.assertRaisesRegex(checker.CheckError, "Bare conditional"):
            self.check(self.source + "\nendif\n")

    def test_shared_headers_hidden_on_right_are_rejected(self):
        hidden = "#if defined(VELVET_RIGHT)\n" + self.headers + "\n#endif"
        with self.assertRaisesRegex(checker.CheckError, r"left.*Common headers"):
            self.check(self.source.replace(self.headers, hidden))

    def test_kconfig_shield_guard_does_not_supply_common_headers(self):
        hidden = "#if defined(CONFIG_SHIELD_VELVET_RIGHT)\n" + self.headers + "\n#endif"
        with self.assertRaisesRegex(checker.CheckError, r"left.*Common headers"):
            self.check(self.source.replace(self.headers, hidden))

    def test_malformed_conditional_in_local_include_is_rejected(self):
        (self.root / "pointer.dtsi").write_text("#if defined(VELVET_RIGHT)\n")
        with self.assertRaisesRegex(checker.CheckError, "preprocessor rejected"):
            self.check()

    def test_local_include_keeps_half_condition(self):
        self.keymap.write_text(self.source)
        left, left_headers = checker.preprocess(self.keymap, checker.HALF_DEFINES["left"])
        right, right_headers = checker.preprocess(self.keymap, checker.HALF_DEFINES["right"])
        self.assertNotIn("trackball_listener", left)
        self.assertIn("trackball_listener", right)
        runtime_header = "input/processors/runtime-input-processor.dtsi"
        self.assertNotIn(runtime_header, left_headers)
        self.assertIn(runtime_header, right_headers)

    def test_disabled_missing_local_include_is_not_opened(self):
        self.check(self.source + '\n#if 0\n#include "not-installed.h"\n#endif\n')

    def test_active_missing_local_include_is_rejected(self):
        with self.assertRaisesRegex(checker.CheckError, "preprocessor rejected"):
            self.check(self.source + '\n#include "not-installed.h"\n')

    def test_wrong_physical_binding_count_is_rejected(self):
        for replacement in ("", "&kp A &kp B"):
            with self.subTest(replacement=replacement):
                with self.assertRaisesRegex(checker.CheckError, "expected 61"):
                    self.check(self.source.replace("&kp GRAVE", replacement))

    def test_combo_position_outside_matrix_is_rejected(self):
        with self.assertRaisesRegex(checker.CheckError, "Invalid position 61"):
            self.check(self.source.replace("<51 52>", "<51 61>"))

    def test_custom_hold_tap_layer_outside_keymap_is_rejected(self):
        with self.assertRaisesRegex(checker.CheckError, "Invalid layer 2"):
            self.check(self.source.replace("&custom_layer_tap SECOND", "&custom_layer_tap 2"))

    def test_pointer_layer_outside_keymap_is_rejected(self):
        path = self.root / "pointer.dtsi"
        path.write_text(path.read_text().replace("<SECOND>", "<9>"))
        with self.assertRaisesRegex(checker.CheckError, "right.*Invalid layer 9"):
            self.check()

    def test_built_in_layer_reference_outside_keymap_is_rejected(self):
        with self.assertRaisesRegex(checker.CheckError, "Invalid layer 9"):
            self.check(self.source.replace("&kp GRAVE", "&mo 9"))


if __name__ == "__main__":
    unittest.main()
