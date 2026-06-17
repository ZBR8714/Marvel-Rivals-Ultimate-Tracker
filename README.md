# Marvel Rivals Ult Tracker

A transparent on-screen overlay that tracks enemy/ally ultimate cooldowns in Marvel Rivals.

## Setup

1. Download the repo as a ZIP and extract it (images and `_run.bat` are already included).
2. Double-click `_run.bat`.

The .bat file will check for Python, install any missing dependencies, then launch the tracker.

## Requirements

- Windows
- Python 3.9+ (install from [python.org](https://www.python.org/downloads/) — check "Add python.exe to PATH" during install)

## Image Naming Format

Images are already included inside the `ults` folder, named like this:

```
ults/
  enemy_cloak_ult.png
  enemy_fox_ult.png
  enemy_gambit_ult.png
  enemy_invis_ult.png
  enemy_luna_ult.png
  enemy_mantis_ult.png
  enemy_rocket_ult.png
  ally_cloak_ult.png
  ally_fox_ult.png
  ally_gambit_ult.png
  ally_invis_ult.png
  ally_luna_ult.png
  ally_mantis_ult.png
  ally_rocket_ult.png
```

## Config

Open `ult_tracker.py` and edit the **USER CONFIG** section at the top to adjust detection mode, ult durations, circle size, and more.

## Stopping the Overlay

Close the terminal window that opened when you ran the .bat file.