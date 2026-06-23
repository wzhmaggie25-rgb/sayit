"""Typeless-style float overlay — pure tkinter, created/destroyed on demand."""
import logging, math, time, threading
import tkinter as tk

logger = logging.getLogger(__name__)

_win = None
_running = False
_start_time = 0.0
_level = 0.0
_root = None


def _ensure_root():
    global _root
    if _root is None:
        _root = tk.Tk()
        _root.withdraw()


def show_overlay(text: str = ""):
    global _win, _running, _start_time, _level
    if _running:
        return
    _running = True
    _start_time = time.time()
    _level = 0.0

    def _build():
        global _win
        try:
            _ensure_root()
            _win = tk.Toplevel(_root)
            _win.overrideredirect(True)
            _win.attributes("-topmost", True)
            _win.configure(bg="#2a2a2a")
            _win.geometry("280x52+{}+{}".format(
                (_win.winfo_screenwidth()-280)//2,
                _win.winfo_screenheight()//2-26))

            # Canvas for waveform
            c = tk.Canvas(_win, width=280, height=52, bg="#2a2a2a",
                          highlightthickness=0, bd=0)
            c.pack()

            def _anim():
                if not _running:
                    return
                c.delete("all")
                # Timer text
                elapsed = int(time.time() - _start_time)
                m, s = divmod(elapsed, 60)
                c.create_text(230, 14, text=f"{m:02d}:{s:02d}",
                              fill="#888888", font=("Segoe UI", 8), anchor="ne")
                c.create_text(230, 34, text="recording",
                              fill="#555555", font=("Segoe UI", 7), anchor="ne")
                # Waveform bars
                bars = 22
                bar_w = 3
                gap = 2
                total_w = bars * (bar_w + gap) - gap
                sx = (170 - total_w) / 2 + 50
                t = time.time() * 10
                for i in range(bars):
                    amp = 0.3 + 0.7 * _level
                    h = max(2, int(2 + 18 * amp * (0.5 + 0.5 * math.sin(t + i * 0.35))))
                    x0 = sx + i * (bar_w + gap)
                    y0 = (52 - h) / 2
                    c.create_rectangle(x0, y0, x0 + bar_w, y0 + h,
                                       fill="#4d8bff", outline="")
                # Status dot
                pulse = (math.sin(time.time() * 4) + 1) / 2
                r = int(255)
                g = int(50 + 50 * pulse)
                b = int(50 + 50 * pulse)
                color = f"#{r:02x}{g:02x}{b:02x}"
                c.create_oval(18, 20, 28, 30, fill=color, outline="")
                _win.after(50, _anim)

            _anim()
            _win.mainloop()
        except Exception as e:
            logger.debug("Overlay error: %s", e)

    threading.Thread(target=_build, daemon=True, name="float-overlay").start()


def hide_overlay():
    global _win, _running
    _running = False
    try:
        if _win:
            _win.destroy()
            _win = None
    except Exception:
        pass


def update_overlay_text(text: str):
    pass


def update_overlay_level(level: float):
    global _level
    _level = min(1.0, max(0.0, level))
