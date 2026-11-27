<div align="center">

# 💐 Flowr.TUI

**An animated, interactive ASCII flower bouquet for your terminal.**

Mix ten flower varieties, tune motion and effects live, choose how much detail to render, and keep your settings between runs.

![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Colour: 256 and truecolor](https://img.shields.io/badge/colour-256%20%7C%20truecolor-ff69b4?style=flat-square)
![License](https://img.shields.io/github/license/KatsukiiNeko/Ascii-Flower?style=flat-square)
![Bouquet](https://img.shields.io/badge/%F0%9F%8C%B8-Flowr.TUI-ff69b4?style=flat-square)

[Quick start](#-quick-start) · [Controls](#-controls) · [Look and detail](#-look-and-detail) · [Presets](#-presets) · [Settings](#-settings) · [CLI](#-command-line) · [Add a flower](#-add-a-flower)

</div>

> [!IMPORTANT]
> flowr.TUI was made with AI assistance, a.k.a. vibe-coding, but a human being will review the code. If you have strong negative feelings about AI-assisted projects, feel free to keep scrolling. Thanks.

---

## ✨ Highlights

- 🌹 **Ten flower varieties**, freely mixed in one bouquet
- 🎨 **Nine curated colour themes** that coordinate flowers, wrap, ribbon, hearts and message colours
- 🔍 **Selectable detail** from `32` to `256` samples, drawn as shape-matched ASCII, half-blocks, braille or sextants
- 🌿 **Greenery and falling petals**: eucalyptus, fern or wheat sprigs, plus petals that drift behind the bouquet
- 💗 **Live controls** for motion, effects, FPS and the caption, all adjustable while it runs
- 💾 **Persistent settings** and built-in presets
- 🐍 **Standard library only** at runtime. NumPy is optional and speeds up the high detail levels

## Quick start

```sh
python -m bouquet
```

Prefer a console command? Install the package, then run `bouquet`:

```sh
python -m pip install .
bouquet
```

Add the optional NumPy speed-up for the `128` and `256` detail levels:

```sh
python -m pip install ".[fast]"
```

> [!NOTE]
> Tested in this workspace on Linux with Python 3.12 and a pseudo-terminal using `TERM=xterm-256color`. Windows, macOS, and named terminal emulators were not verified.

> [!TIP]
> If hearts or dots look misaligned in your terminal, run with `--ascii` to avoid ambiguous-width glyphs.

## ⌨️ Controls

Every action is also available in the settings panel.

**Playback**

| Key | Action |
| --- | --- |
| `Space` | Pause or resume |
| `r` | Reset animation |
| `+` / `-` | Change target FPS |
| `s` | Shuffle the seed |
| `m` | Edit message |

**Settings panel**

| Key | Action |
| --- | --- |
| `Tab` | Open or close settings |
| `↑` / `↓` | Select a setting |
| `←` / `→` | Adjust a setting |
| `Shift` + arrow, `PageUp` / `PageDown` | Coarse adjustment |
| `Enter` | Activate or edit |
| `[` / `]`, `1`–`6` | Previous or next tab, or jump straight to a tab |

**App**

| Key | Action |
| --- | --- |
| `?` | Help |
| `D` | Restore defaults (asks for confirmation) |
| `q`, `Ctrl+C` | Quit |

**Editing the message.** Unicode is supported. Use `Home`/`End` and the arrow keys to move, `Backspace`/`Delete` to remove text, `Enter` to save and `Esc` to cancel.

## 🎨 Look and detail

The **Look** tab collects the rendering controls.

| Setting | Options | What it does |
| --- | --- | --- |
| **Detail** | `auto`, `32`, `64`, `128`, `256` | Sets the height of the square sample canvas. Higher levels resolve cell edges with a 4x8 glyph-mask match. Auto matches the terminal size and lowers detail if the frame rate falls. |
| **Style** | `ascii`, `half`, `braille`, `sextant` | Draws samples as shape-matched ASCII glyphs, half blocks, braille dots or legacy-computing sextants. Falls back to ascii on limited terminals. |
| **Colour mode** | `auto`, `256`, `truecolor`, `mono` | Chooses how colour is emitted. |
| **Theme** | nine curated themes | Coordinates flowers, wrap, ribbon, hearts and message colours. |
| **Greenery** | eucalyptus, fern, wheat | Adds sprigs around the flowers. |
| **Petal fall** | on / off, amount | Sheds visible petals behind the bouquet. |

Optional NumPy (`pip install ".[fast]"`) speeds up the `128` and `256` detail levels.

## 🌸 Presets

| Preset | Notes |
| --- | --- |
| `Classic` | The reference composition and seed. |
| `Minimal` | No hearts, filler, ribbon, sway or head bob. Keeps flowers, stems, leaves and wrap. |
| `Spring Garden` | Built-in |
| `Romantic Reds` | Built-in |
| `Sunny Field` | Built-in |
| `Wildflower Mix` | Built-in |

Aliases are also available: `Pastel`, `Midnight` and `Wildflower`.

## 💾 Settings

Settings are saved automatically to your platform's config directory, and writes are atomic. Pass `--no-config` to disable reading and writing entirely.

| Platform | Config file |
| --- | --- |
| Linux | `$XDG_CONFIG_HOME/bouquet/config.json` if set, otherwise `~/.config/bouquet/config.json` |
| macOS | `~/Library/Application Support/Bouquet/config.json` |
| Windows | `%APPDATA%/Bouquet/config.json` |

## Command line

```sh
python -m bouquet --preset Classic --theme blush --detail 128 --style half
```

<details>
<summary><strong>All options</strong></summary>

```text
--config PATH       Use a config file
--no-config         Ignore and do not save config
--preset NAME       Start from a preset
--theme NAME        Colour theme (classic, blush, moonlight, rainbow, ...)
--detail LEVEL      Sample detail: auto, 32, 64, 128 or 256
--style STYLE       Glyph style: ascii, half or braille
--greenery N        Greenery sprigs (0-20)
--color-mode MODE   Colour: auto, 256, truecolor or mono
--fps N             Set target FPS (5-60)
--message TEXT      Set the caption
--seed N            Set composition seed
--ascii             Use ASCII-safe glyph substitutions
--no-color          Disable ANSI colour (also honours NO_COLOR)
--gallery           Print the ten flower varieties and exit
--snapshot [PATH]   Render one frame to stdout or PATH
--at SECONDS        Set snapshot or starting animation time
```

When stdin or stdout is not a TTY, or `TERM=dumb`, the app prints one plain snapshot and exits. `--gallery` and `--snapshot` are intended for non-interactive use.

</details>

## Checks

Run the standard-library test suite:

```sh
python -m unittest discover -v
```

## Credits

Flowr.TUI includes material derived from **Ascii-Flower-Bouquet** by Alish Sharma (MIT).
See [`NOTICE`](NOTICE) for the upstream license and copyright.

## License

MIT License. See `LICENSE` for details.

---

© 2026 Katsukii Neko. Licensed under the MIT License.
