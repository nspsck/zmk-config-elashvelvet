# Little Dragon display artwork

Chibi fan-art interpretation of the white-haired GPT dragon girl, whose design
is credited to **ZipZipPipe** on the
[user-selected reference page](https://genderswapai.com/zh-CN/ai-gijinka/gpt).
The concept uses her hair, horns, wings, curled tail and dress. No CrossPet sprite
files are included.

The concept and sprite sheet were generated with the **built-in imagegen tool**.
The user approved the horizontal concept before implementation. The page's
character description informed the concept; its original image downloads were
unavailable. The approved concept was then supplied as the sprite-generation
reference.

| File | Purpose |
| --- | --- |
| `approved-concept.png` | Approved enlarged style/layout proposal |
| `concept-prompt.txt` | Exact concept prompt |
| `dragon-source.png` | Original generated 2×2 sheet, unmodified |
| `sprite-prompt.txt` | Exact sprite generation prompt |
| `preview-native.png` | Actual renderer, both 160×68 displays side by side |
| `preview.png` | Same pixels enlarged 4× |
| `preview.gif` | Actual four-frame artwork with firmware timing, enlarged 4× |
| `status-examples.png` | Scroll, precision, USB/layer, and disconnected examples |

`scripts/pack_dragon_art.py` area-samples the source to a 128×104 sheet,
thresholds without dithering, and packs four 64×52 frames row-major/MSB-first.
Frame order is idle, blink, tail sway, wave; a set bit means physically white.
The generated `src/display/dragon_assets.c` and `.h` are committed so the ZMK
build only needs C sources. The source PNG's SHA-256 is recorded in the C file.

`scripts/check_display.py --preview` compiles and executes the very same portable
renderer used by the firmware; the preview's typography and sprites are its
actual pixels. Battery values are sample data. It does not simulate the display
driver, wireless connection or physical sensor, which require firmware builds
and device testing.
