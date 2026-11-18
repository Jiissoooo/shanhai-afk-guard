"""check_tray_live.py - 检查正在运行的实例是否真的注册了托盘图标。"""
from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes as wt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import winapi as W  # noqa: E402

user32 = W.user32
user32.FindWindowExW.argtypes = [wt.HWND, wt.HWND, wt.LPCWSTR, wt.LPCWSTR]
user32.FindWindowExW.restype = wt.HWND
user32.IsWindow.argtypes = [wt.HWND]
user32.IsWindow.restype = wt.BOOL

HWND_MESSAGE = wt.HWND(-3)


def main() -> int:
    print("=" * 64)
    print(" 现场检查：托盘是否已注册")
    print("=" * 64)

    # message-only 窗口必须是其父为 HWND_MESSAGE，用 FindWindowEx 向下找
    # 先拿到所有可能的类名：ShanhaiTray_<pid>_<id>
    hits = []
    for pid_probe in set():
        pass

    # 直接遍历：用 EnumWindows 找不到 message-only 窗口，
    # 改用 FindWindowEx(HWND_MESSAGE, ...) 逐个枚举其子窗口
    child = user32.FindWindowExW(HWND_MESSAGE, None, None, None)
    count = 0
    while child:
        cnt = count
        count += 1
        if count > 500:
            break
        try:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(child, buf, 256)
            cls = buf.value
            if cls.startswith("ShanhaiTray"):
                tlen = user32.GetWindowTextLengthW(child)
                tbuf = ctypes.create_unicode_buffer(tlen + 2)
                user32.GetWindowTextW(child, tbuf, tlen + 1)
                hits.append((child, cls, tbuf.value))
        except Exception:
            pass
        child = user32.FindWindowExW(HWND_MESSAGE, child, None, None)

    print(f"\nmessage-only 窗口总数: {count}")
    print(f"其中 ShanhaiTray 窗口: {len(hits)}")
    for h, cls, title in hits:
        print(f"  hwnd=0x{int(h):X}  cls={cls}")
        print(f"             title={title!r}")

    print()
    if hits:
        print("结论: 托盘窗口已在系统中注册 —— 托盘图标应显示在右下角")
        return 0
    print("结论: 未找到托盘窗口")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
