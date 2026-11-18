"""shot.py - 在指定权限下自行截图（GUI 由本会话启动，同完整性可直接捕获）。"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes as wt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import winapi as W  # noqa: E402

user32 = W.user32
gdi32 = ctypes.WinDLL("gdi32")
user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
user32.PrintWindow.restype = wt.BOOL
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(W.RECT)]
user32.GetDC.argtypes = [wt.HWND]
user32.GetDC.restype = wt.HDC
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wt.HDC]
gdi32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT,
                            ctypes.c_void_p, ctypes.c_void_p, wt.UINT]
gdi32.GetDIBits.restype = ctypes.c_int


def save_bmp(path, hwnd):
    r = W.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        return False, "bad size"
    hdc = user32.GetDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    ok = user32.PrintWindow(hwnd, mdc, 2)
    gdi32.SelectObject(mdc, old)

    # 取像素并写 32 位 BMP
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long),
                    ("biHeight", ctypes.c_long), ("biPlanes", wt.WORD),
                    ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                    ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
                    ("biClrImportant", wt.DWORD)]

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -h
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, ctypes.cast(buf, ctypes.c_void_p),
                    ctypes.byref(bi), 0)

    fileh = w * h * 4 + 54
    hdr = bytearray(54)
    hdr[0:2] = b"BM"
    hdr[2:6] = fileh.to_bytes(4, "little")
    hdr[10:14] = (54).to_bytes(4, "little")
    hdr[14:18] = (40).to_bytes(4, "little")
    hdr[18:22] = w.to_bytes(4, "little")
    hdr[22:26] = h.to_bytes(4, "little")
    hdr[26:28] = (1).to_bytes(2, "little")
    hdr[28:30] = (32).to_bytes(2, "little")
    hdr[34:38] = (w * h * 4).to_bytes(4, "little")
    with open(path, "wb") as fh:
        fh.write(hdr)
        fh.write(buf.raw[:w * h * 4])

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)
    return ok, f"{w}x{h}"


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "artifacts", "shot.bmp")
    launch = "--launch" in sys.argv
    proc = None
    if launch:
        proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "main.py")])
        time.sleep(5)
    try:
        # 精确定位：必须是 python.exe 启动的、标题以"山海寻灵 ·"开头的窗口，
        # 避免命中 DeepSeek Harness 里含"山海寻灵"字样的那个窗口。
        wins = [w for w in W.list_windows(include_hidden=True)
                if w["exe"].lower().startswith("python")
                and (w["title"] or "").startswith("山海寻灵")]
        if not wins:
            print("NO WINDOW (python.exe / 山海寻灵 · ...)")
            for w in W.list_windows(include_hidden=True):
                if "山海" in (w["title"] or ""):
                    print(f"  candidate: exe={w['exe']} title={w['title']!r}")
            return 1
        w = wins[0]
        me = __import__("app.integrity", fromlist=["x"]).self_integrity()
        il = __import__("app.integrity", fromlist=["x"]).il_name(me)
        ok, size = save_bmp(out, w["hwnd"])
        print(f"hwnd=0x{w['hwnd']:X} PrintWindow={ok} size={size} selfIL={il}")
        return 0
    finally:
        if proc:
            time.sleep(0.5)


if __name__ == "__main__":
    raise SystemExit(main())
