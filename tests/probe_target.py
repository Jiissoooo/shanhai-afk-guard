"""probe_target.py - 测试用假目标窗口。

一个纯 Win32 窗口，收到 WM_KEYDOWN 就往日志文件追加一行。
用于验证：后台投递、最小化投递、多窗口并发。
    python tests/probe_target.py <窗口标题> <日志文件> [minimize]
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes as wt

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_KEYUP = 0x0101
SW_MINIMIZE = 6
CS_HREDRAW, CS_VREDRAW = 0x0002, 0x0001
WS_OVERLAPPEDWINDOW = 0x00CF0000
CW_USEDEFAULT = 0x80000000

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT,
                             wt.WPARAM, wt.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wt.HWND), ("message", wt.UINT),
                ("wParam", wt.WPARAM), ("lParam", wt.LPARAM),
                ("time", wt.DWORD), ("pt_x", ctypes.c_long),
                ("pt_y", ctypes.c_long)]


user32.CreateWindowExW.restype = wt.HWND
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, wt.HWND, wt.HMENU,
                                   wt.HINSTANCE, wt.LPVOID]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wt.HWND, wt.UINT, wt.UINT]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]


def main():
    title = sys.argv[1] if len(sys.argv) > 1 else "AFKPROBE"
    logpath = sys.argv[2] if len(sys.argv) > 2 else "probe.log"
    do_min = len(sys.argv) > 3 and sys.argv[3] == "minimize"

    hinst = kernel32.GetModuleHandleW(None)
    cls = f"ProbeWnd_{title}_{int(time.time()*1000) % 100000}"

    def wndproc(hwnd, msg, wp, lp):
        if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
            with open(logpath, "a", encoding="utf-8") as fh:
                fh.write(f"{time.time():.3f}\tVK=0x{int(wp):02X}\tmsg=0x{msg:04X}\n")
            return 0
        if msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wp, lp)

    cb = WNDPROC(wndproc)
    wc = WNDCLASSW()
    wc.style = CS_HREDRAW | CS_VREDRAW
    wc.lpfnWndProc = cb
    wc.hInstance = hinst
    wc.lpszClassName = cls
    wc.hbrBackground = ctypes.cast(6, wt.HBRUSH)

    if not user32.RegisterClassW(ctypes.byref(wc)):
        print(f"RegisterClassW 失败: {ctypes.get_last_error()}")
        return 1

    hwnd = user32.CreateWindowExW(0, cls, title, WS_OVERLAPPEDWINDOW,
                                  CW_USEDEFAULT, CW_USEDEFAULT, 420, 200,
                                  None, None, hinst, None)
    if not hwnd:
        print(f"CreateWindowExW 失败: {ctypes.get_last_error()}")
        return 1

    user32.ShowWindow(hwnd, SW_MINIMIZE if do_min else 5)
    with open(logpath, "a", encoding="utf-8") as fh:
        fh.write(f"# READY hwnd=0x{hwnd:X} pid={ctypes.windll.kernel32.GetCurrentProcessId()}\n")

    msg = MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
