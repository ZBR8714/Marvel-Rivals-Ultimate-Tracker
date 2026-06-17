import warnings
warnings.filterwarnings("ignore")
"""
Marvel Rivals Ult Tracker Overlay
==================================
CONFIG: Edit the section below before running.

Requirements:
    pip install opencv-python mss easyocr numpy Pillow pywin32

Template images must be in the "ults" subfolder next to this script.
Enemy: enemy_cloak_ult.png, enemy_fox_ult.png, enemy_gambit_ult.png,
       enemy_invis_ult.png, enemy_luna_ult.png, enemy_mantis_ult.png,
       enemy_rocket_ult.png
Ally:  ally_cloak_ult.png, ally_fox_ult.png, ally_gambit_ult.png,
       ally_invis_ult.png, ally_luna_ult.png, ally_mantis_ult.png,
       ally_rocket_ult.png
"""

# ─────────────────────────────────────────────
#  USER CONFIG
# ─────────────────────────────────────────────

# Detection mode: "template" (image match) or "ocr" (easyocr text match)
DETECTION_MODE = "template"

# Template matching confidence threshold (0.0 – 1.0)
TEMPLATE_THRESHOLD = 0.75

# OCR confidence threshold (0.0 – 1.0)
OCR_THRESHOLD = 0.5

# Scan interval in seconds
SCAN_INTERVAL = 0.1

# Subtitle scan region as fraction of screen: (left, top, right, bottom)
# Based on 1440p screenshot analysis — subtitles sit in lower-centre
SUBTITLE_REGION = (0.30, 0.72, 0.70, 0.92)

# Ult durations in seconds — edit these values
ULT_DURATIONS = {
    "Cloak":   11.5,
    "Fox":     10.5,
    "Gambit":  8,
    "Invis":   8,
    "Luna":    10,
    "Mantis":  8,
    "Rocket":  12,
}

# OCR phrases to match per hero, per side (lowercase, partial match)
# Enemy lines are the known in-game subtitle lines
# Ally lines are placeholders — replace with real values when known
OCR_ENEMY_KEYWORDS = {
    "Cloak":   ["us against the world"],
    "Fox":     ["정의의 시간"],
    "Gambit":  ["gambit never folds"],
    "Invis":   ["disappear"],
    "Luna":    ["i am ready to put on a show"],
    "Mantis":  ["we are undefeatable"],
    "Rocket":  ["this is real firepower"],
}

OCR_ALLY_KEYWORDS = {
    "Cloak":   ["placeholder ally cloak line"],
    "Fox":     ["placeholder ally fox line"],
    "Gambit":  ["placeholder ally gambit line"],
    "Invis":   ["placeholder ally invis line"],
    "Luna":    ["placeholder ally luna line"],
    "Mantis":  ["placeholder ally mantis line"],
    "Rocket":  ["placeholder ally rocket line"],
}

# Max simultaneous ults displayed per side
MAX_PER_SIDE = 6

# Circle size in pixels (scales with resolution automatically — this is the 1080p base)
BASE_CIRCLE_RADIUS = 65
BASE_FONT_SIZE_TITLE = 14
BASE_FONT_SIZE_TIME  = 21

# ─────────────────────────────────────────────
#  END USER CONFIG
# ─────────────────────────────────────────────

import os
import sys
import time
import math
import threading
import ctypes
import ctypes.wintypes
import tkinter as tk
from tkinter import font as tkfont

import cv2
import mss
import numpy as np
from PIL import Image, ImageTk

# Lazy-load easyocr only when needed
_ocr_reader = None

def get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        _ocr_reader = easyocr.Reader(["en", "ko"], gpu=False, verbose=False)
    return _ocr_reader


# ─── Win32 click-through helpers ─────────────────────────────────────────────

GWL_EXSTYLE     = -20
WS_EX_LAYERED   = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

def make_clickthrough(hwnd):
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(
        hwnd, GWL_EXSTYLE,
        style | WS_EX_LAYERED | WS_EX_TRANSPARENT
    )


# ─── Scale helpers ────────────────────────────────────────────────────────────

def get_scale(screen_h):
    """Return scale factor relative to 1080p."""
    return screen_h / 1080.0


# ─── Active ult state ─────────────────────────────────────────────────────────

class ActiveUlt:
    def __init__(self, hero, side, duration):
        self.hero      = hero
        self.side      = side          # "ally" or "enemy"
        self.duration  = duration
        self.started   = time.time()
        self.id        = f"{side}_{hero}_{self.started}"

    @property
    def elapsed(self):
        return time.time() - self.started

    @property
    def remaining(self):
        return max(0.0, self.duration - self.elapsed)

    @property
    def fraction(self):
        """1.0 = full, 0.0 = expired."""
        return self.remaining / self.duration

    @property
    def expired(self):
        return self.elapsed >= self.duration


# ─── Overlay window ──────────────────────────────────────────────────────────

class OverlayWindow:
    PADDING     = 10   # px between circles (scaled)
    TOP_OFFSET  = 0.10 # 10% from top of screen

    def __init__(self, screen_w, screen_h):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.scale    = get_scale(screen_h)

        self.radius    = int(BASE_CIRCLE_RADIUS * self.scale)
        self.diameter  = self.radius * 2
        self.padding   = int(self.PADDING * self.scale)
        self.font_title_size = max(7, int(BASE_FONT_SIZE_TITLE * self.scale))
        self.font_time_size  = max(9, int(BASE_FONT_SIZE_TIME  * self.scale))

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "black")
        self.root.configure(bg="black")
        self.root.geometry(f"{screen_w}x{screen_h}+0+0")

        self.canvas = tk.Canvas(
            self.root,
            width=screen_w,
            height=screen_h,
            bg="black",
            highlightthickness=0
        )
        self.canvas.pack()

        # Make click-through after window is created
        self.root.update_idletasks()
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        # Use the tkinter HWND
        hwnd = ctypes.windll.user32.FindWindowW(None, self.root.title())
        make_clickthrough(int(self.root.frame(), 16))

        self.active_ults: list[ActiveUlt] = []
        self.lock = threading.Lock()

        self._draw_loop()

    def add_ult(self, hero, side):
        """Called from scanner thread."""
        with self.lock:
            # Prevent duplicate
            for u in self.active_ults:
                if u.hero == hero and u.side == side and not u.expired:
                    return
            side_ults = [u for u in self.active_ults if u.side == side]
            if len(side_ults) >= MAX_PER_SIDE:
                return
            duration = ULT_DURATIONS.get(hero, 10)
            self.active_ults.append(ActiveUlt(hero, side, duration))

    def _draw_loop(self):
        self._render()
        self.root.after(100, self._draw_loop)   # ~10 fps overlay refresh

    def _render(self):
        self.canvas.delete("all")
        with self.lock:
            # Prune expired
            self.active_ults = [u for u in self.active_ults if not u.expired]
            allies  = [u for u in self.active_ults if u.side == "ally"]
            enemies = [u for u in self.active_ults if u.side == "enemy"]

        top_y = int(self.screen_h * self.TOP_OFFSET)
        step  = self.diameter + self.padding * 3 + self.font_title_size + 4

        # Left column: allies at 40% from left
        ally_x = int(self.screen_w * 0.40)
        for i, ult in enumerate(allies[:MAX_PER_SIDE]):
            cx = ally_x
            cy = top_y + self.radius + i * step
            self._draw_circle(cx, cy, ult, "#4488FF")

        # Right column: enemies at 60% from left
        enemy_x = int(self.screen_w * 0.60)
        for i, ult in enumerate(enemies[:MAX_PER_SIDE]):
            cx = enemy_x
            cy = top_y + self.radius + i * step
            self._draw_circle(cx, cy, ult, "#FF4444")

    def _draw_circle(self, cx, cy, ult: ActiveUlt, color: str):
        r  = self.radius
        x0 = cx - r
        y0 = cy - r
        x1 = cx + r
        y1 = cy + r

        # Background circle (dark semi-transparent grey via stipple)
        self.canvas.create_oval(x0, y0, x1, y1, fill="#1a1a1a", outline="", stipple="gray50")

        # Arc: fraction of circle remaining, starts at top (-90°)
        extent = ult.fraction * 360
        self.canvas.create_arc(
            x0, y0, x1, y1,
            start=90,
            extent=extent,
            style=tk.ARC,
            outline=color,
            width=max(3, int(5 * self.scale))
        )

        # Time remaining text
        secs = f"{ult.remaining:.1f}"
        self.canvas.create_text(
            cx, cy,
            text=secs,
            fill="white",
            font=("Consolas", self.font_time_size, "bold")
        )

        # Title above circle
        self.canvas.create_text(
            cx, y0 - 4,
            text=f"{ult.hero} Ult",
            fill=color,
            font=("Consolas", self.font_title_size, "bold"),
            anchor="s"
        )

    def run(self):
        self.root.mainloop()


# ─── Scanner ─────────────────────────────────────────────────────────────────

class UltScanner:
    def __init__(self, overlay: OverlayWindow, screen_w, screen_h):
        self.overlay  = overlay
        self.screen_w = screen_w
        self.screen_h = screen_h

        # Compute absolute subtitle region
        l, t, r, b = SUBTITLE_REGION
        self.region = {
            "left":   int(screen_w * l),
            "top":    int(screen_h * t),
            "width":  int(screen_w * (r - l)),
            "height": int(screen_h * (b - t)),
        }

        # Pre-load templates
        self.templates = self._load_templates()
        self._running = True

    def _load_templates(self):
        """Load and grayscale all template images from the ults subfolder."""
        script_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ults")
        heroes = list(ULT_DURATIONS.keys())
        sides  = ["ally", "enemy"]
        templates = {}
        for side in sides:
            for hero in heroes:
                fname = f"{side}_{hero.lower()}_ult.png"
                fpath = os.path.join(script_dir, fname)
                if os.path.exists(fpath):
                    img = cv2.imread(fpath, cv2.IMREAD_GRAYSCALE)
                    if img is not None:
                        templates[(side, hero)] = img
                        print(f"[+] Loaded template: {fname}")
                    else:
                        print(f"[!] Failed to read: {fname}")
                else:
                    print(f"[-] Missing template (will skip): {fname}")
        return templates

    def _capture_region(self):
        """Capture subtitle region as grayscale numpy array."""
        with mss.mss() as sct:
            shot = sct.grab(self.region)
        img = np.frombuffer(shot.raw, dtype=np.uint8).reshape(
            shot.height, shot.width, 4
        )
        gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
        return gray

    def _scan_template(self, gray):
        """Return list of (side, hero) detections via template matching."""
        detected = []
        for (side, hero), tmpl in self.templates.items():
            # Resize template if it's larger than capture region
            th, tw = tmpl.shape
            rh, rw = gray.shape
            if th > rh or tw > rw:
                continue
            result = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            if max_val >= TEMPLATE_THRESHOLD:
                detected.append((side, hero))
        return detected

    def _scan_ocr(self, gray):
        """Return list of (side, hero) detections via EasyOCR."""
        reader   = get_ocr_reader()
        results  = reader.readtext(gray, detail=1, paragraph=False)
        detected = []
        for (_, text, conf) in results:
            if conf < OCR_THRESHOLD:
                continue
            text_lower = text.lower()
            for hero, keywords in OCR_ENEMY_KEYWORDS.items():
                for kw in keywords:
                    if kw in text_lower:
                        detected.append(("enemy", hero))
                        break
            for hero, keywords in OCR_ALLY_KEYWORDS.items():
                for kw in keywords:
                    if kw in text_lower:
                        detected.append(("ally", hero))
                        break
        return detected

    def scan_loop(self):
        """Run in background thread."""
        # Cooldown per (side, hero) to avoid re-triggering mid-ult
        cooldowns: dict[tuple, float] = {}

        while self._running:
            try:
                gray = self._capture_region()

                if DETECTION_MODE == "template":
                    detections = self._scan_template(gray)
                else:
                    detections = self._scan_ocr(gray)

                now = time.time()
                for (side, hero) in detections:
                    key = (side, hero)
                    duration = ULT_DURATIONS.get(hero, 10)
                    last = cooldowns.get(key, 0)
                    # Only re-trigger after ult would have expired
                    if now - last >= duration:
                        cooldowns[key] = now
                        self.overlay.add_ult(hero, side)

            except Exception as e:
                print(f"[scan error] {e}")

            time.sleep(SCAN_INTERVAL)

    def stop(self):
        self._running = False


# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    # Get primary monitor resolution
    user32    = ctypes.windll.user32
    screen_w  = user32.GetSystemMetrics(0)
    screen_h  = user32.GetSystemMetrics(1)
    print(f"[*] Detected resolution: {screen_w}x{screen_h}")
    print(f"[*] Detection mode: {DETECTION_MODE}")
    print(f"[*] Subtitle region (px): {dict(left=int(screen_w*SUBTITLE_REGION[0]), top=int(screen_h*SUBTITLE_REGION[1]), right=int(screen_w*SUBTITLE_REGION[2]), bottom=int(screen_h*SUBTITLE_REGION[3]))}")

    overlay = OverlayWindow(screen_w, screen_h)
    scanner = UltScanner(overlay, screen_w, screen_h)

    scan_thread = threading.Thread(target=scanner.scan_loop, daemon=True)
    scan_thread.start()

    try:
        overlay.run()
    except KeyboardInterrupt:
        pass
    finally:
        scanner.stop()


if __name__ == "__main__":
    main()
