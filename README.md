# Open Screen for Mars Gaming ML-VISIONPRO240

![Hardware](https://img.shields.io/badge/Hardware-Mars_Gaming_ML--VISIONPRO240-red)
![Chipset](https://img.shields.io/badge/Chipset-MacroSilicon_MS9132-blue)
![Platform](https://img.shields.io/badge/Platform-Linux-green)
![Python](https://img.shields.io/badge/Python-3.10%2B-yellow)
![GUI](https://img.shields.io/badge/GUI-PySide6_(Qt)-41cd52)

**An open-source, native Linux controller for the 480×480 LCD built into the Mars Gaming ML-VISIONPRO240 liquid cooler.**

The cooler ships with a Windows-only tool, so on Linux the screen just stays dark. This project reverse-engineers the USB protocol of the MacroSilicon **MS9132** chip that drives the screen and replaces the vendor software with a fast, threaded Qt application. It shows images, GIFs, videos, live streams, your OBS output, and animated live scenes.

---

## Table of contents

- [Features](#features)
- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Display modes](#display-modes)
- [Project structure](#project-structure)
- [USB protocol notes](#usb-protocol-notes)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [Disclaimer](#disclaimer)

---

## Features

| | |
|---|---|
| 🖼️ **Images and GIFs** | `.jpg`, `.png`, `.webp` and animated `.gif`, played at their native frame timing. |
| 🎞️ **Video playback** | `.mp4`, `.avi`, `.mkv`, `.webm`, decoded frame by frame with OpenCV, so whole videos never sit in RAM. |
| 📺 **Live streams** | Point it at a Twitch/YouTube stream URL and it plays live through [Streamlink](https://streamlink.github.io/). |
| 🎥 **OBS Virtual Camera** | Mirror any OBS scene to the LCD at ~30 FPS. Show temperatures (MangoHud, Conky), a browser, or a game, even on Wayland. |
| 🔄 **Rotation** | 0°, 90°, 180° or 270°, applied instantly. Handy if the pump block is mounted upside down. |
| 📐 **Scaling** | *Crop* keeps the aspect ratio. *Stretch* fills the whole 480×480 screen. |
| 🐾 **Live scenes** | Animated scenes rendered in real time: a desktop pet (shimeji), a procedural 2D sandbox world, block-world scenes with a day/night cycle, and a WorldBox spectator mode. |
| 📂 **Folder watching** | Pick a folder and the media list updates by itself when you add or remove files. |
| 🧵 **Non-blocking design** | The GUI, the media decoder and the low-level USB writer each run on their own thread, so the interface never freezes. |
| 🔓 **No root needed** | The installer adds a `udev` rule so a normal user can talk to the device. |

## How it works

```
┌──────────────┐  load / rotate / scale  ┌────────────────┐  480×480 BGR frames  ┌──────────────┐
│   ui.py      │ ──────────────────────▶ │ media_worker   │ ───────────────────▶ │ usb_worker   │
│  (PySide6)   │                         │   (QThread)    │                      │  (QThread)   │
└──────────────┘                         └────────────────┘                      └──────┬───────┘
                                          images · GIFs · video                         │ PyUSB bulk
                                          streams · OBS · scenes                        ▼
                                                                              MS9132 LCD (VID 345F, PID 9132)
```

1. **`ui.py`**: the Qt main window. You choose media, rotation and scaling here.
2. **`media_worker.py`**: turns the chosen source (file, stream, camera or scene engine) into a stream of 480×480 Pillow frames, then rotates and scales them.
3. **`usb_worker.py`**: converts each frame to the screen's pixel format, wraps it in the frame header and footer, and sends it to the device over USB bulk transfers.

## Requirements

- Linux with `libusb` (it ships with most distributions).
- Python **3.10+** with `venv`.
- The Mars Gaming ML-VISIONPRO240, or another cooler built on the MS9132 with the same USB IDs.
- Optional: **OBS Studio** with the Virtual Camera (`v4l2loopback`) for mirror mode.

Python dependencies (from `requirements.txt`): `PySide6`, `pyusb`, `pillow`, `opencv-python-headless`, `streamlink`, `mss`.

## Installation

```bash
git clone https://github.com/lucaslopezag-eng/open-software-for-ML-VISIONPRO240.git
cd open-software-for-ML-VISIONPRO240
chmod +x install.sh
./install.sh
```

The installer does four things:

1. Creates a Python virtual environment in `./venv`.
2. Installs the dependencies.
3. Adds the udev rule `/etc/udev/rules.d/99-mars-gaming.rules` so the device is usable without root. This is the only step that asks for `sudo`.
4. Adds an **Open Screen for Mars Gaming** entry to your application menu.

<details>
<summary>Manual installation</summary>

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="345f", ATTRS{idProduct}=="9132", MODE="0666"' \
  | sudo tee /etc/udev/rules.d/99-mars-gaming.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```
</details>

## Usage

```bash
./run.sh
```

Or open **Open Screen for Mars Gaming** from your application menu.

1. Choose a folder with images, GIFs or videos. Its files appear in the list.
2. Click an item and it starts playing on the LCD straight away.
3. Change **rotation** and **scaling** at any time. The changes apply live.
4. To mirror OBS: start the Virtual Camera in OBS, then click **Connect to OBS Virtual Camera**. A square output resolution such as 1080×1080 gives the best result.

> The interface text is currently in Spanish. Translations are welcome (see [Contributing](#contributing)).

## Display modes

| Mode | Source | Notes |
|---|---|---|
| Static image | `.jpg` / `.png` / `.webp` | Sent once, then held on screen. |
| GIF | `.gif` | Plays each frame for its own duration. |
| Video | `.mp4` / `.avi` / `.mkv` / `.webm` | Decoded by OpenCV in real time and loops at the end. |
| Live stream | Stream URL | Resolved with Streamlink. |
| OBS camera | Virtual Camera device | Runs at about 30 FPS. |
| Virtual pet | `shimeji_engine.py` | Sprite-based pet that walks around the screen. |
| Sandbox world | `terraria_engine.py` | Procedurally generated 2D world. |
| Block world | `ultra_mc_engine.py`, `masterpiece_mc_engine.py`, `advanced_mc_engine.py` | Block-world scenes with a player and a day/night cycle. |
| WorldBox | `worldbox_engine.py` | Experimental. Launches WorldBox, which you must own, and streams it as a spectator. |

## Project structure

```
main.py                  Entry point: creates the Qt application and main window
ui.py                    Main window (media list, rotation, scaling, OBS button, tray icon)
media_worker.py          Frame producer thread: files, streams, OBS camera, scene engines
usb_worker.py            USB writer thread: frame encoding and bulk transfers
init_cmds.py             Initialization command sequence the MS9132 needs
reproductor.py           Minimal stand-alone CLI player (documents the protocol)
*_engine.py              Live scene engines
assets/                  Sprites used by the scene engines
install.sh / run.sh      Installer and launcher
```

## USB protocol notes

These notes come from reverse-engineering the vendor tool's traffic:

- **Device:** MacroSilicon MS9132, USB `VID 0x345F`, `PID 0x9132`. It uses HID control transfers plus bulk transfers.
- **Resolution:** 480 × 480 px.
- **Pixel format:** BGR888, 3 bytes per pixel. A pixel value of `0xFF` must not appear in the image data, because `0xFF` marks the start of the header and footer.
- **Frame layout:** 8-byte header + 480 × 480 × 3 bytes of pixels + 8-byte footer, so **691,216 bytes** per frame.
  - Header: `FF 00 00 00 00 1E 01 E0`
  - Footer: `FF C0 00 00 00 00 00 00`
- **Initialization:** the screen only accepts frames after a fixed sequence of control transfers, recorded in `init_cmds.py`.

`reproductor.py` is a short reference implementation if you want to drive the screen from your own code.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Screen not found` | Check `lsusb \| grep 345f`. If it shows up, re-run the udev steps, then unplug and replug the cooler's USB cable. |
| `Errno 16 Resource busy` | Another program has the device open, such as a second copy of this app. Close it. The worker also detaches the kernel driver for you. |
| Permission denied | The udev rule is missing. Run `install.sh` again, or follow the manual steps. |
| OBS image looks stretched | Set a square output resolution in OBS (Settings → Video). |
| Choppy video | Pick a lower-resolution source. The USB link tops out at roughly 30 FPS for full frames. |

## Contributing

Bug reports, protocol findings and pull requests are welcome. These would help most:

- Testing on other MS9132-based coolers or screens.
- English (and other) translations of the interface.
- Packaging for Flatpak or AUR.

## Disclaimer

This is an independent community project. It is not affiliated with or endorsed by Mars Gaming or MacroSilicon. All trademarks belong to their owners. You use it at your own risk.
