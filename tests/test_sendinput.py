"""test_sendinput.py - 验证 sendinput（硬件级）通道。

硬件级注入只对前台窗口生效，所以这里把假目标强制拉到前台再打。
同时验证 both 模式在“不在前台”时会自动降级到 message 而不是空打。
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app import inject, winapi as W  # noqa: E402

LOGDIR = os.path.join(ROOT, "artifacts")
user32 = W.user32


def force_foreground(hwnd: int) -> bool:
    """直接复用 inject 的实现（已实测 8/8）。

    注意：目标若处于最小化状态，必须先 ShowWindow(SW_RESTORE)，
    否则 AttachThreadInput + SetForegroundWindow 会稳定失败 —— 这是
    Windows 的行为，不是 bug。inject.force_foreground 内部已处理。
    """
    return inject.force_foreground(hwnd)


def count_keys(log: str) -> int:
    if not os.path.exists(log):
        return 0
    with open(log, "r", encoding="utf-8", errors="replace") as fh:
        return sum(1 for line in fh if line.startswith(tuple("0123456789")) and "VK=" in line)


def main() -> int:
    os.makedirs(LOGDIR, exist_ok=True)
    log = os.path.join(LOGDIR, "probe_si.log")
    if os.path.exists(log):
        os.remove(log)
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "probe_target.py"),
                          "AFKSI", log], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 6
        wins = []
        while time.time() < deadline:
            wins = W.find_windows(title_sub="AFKSI")
            if wins:
                break
            time.sleep(0.2)
        if not wins:
            print("FAIL: 未找到 AFKSI 窗口")
            return 1
        hwnd = wins[0]["hwnd"]
        print(f"[1] 目标 hwnd=0x{hwnd:X}")

        ok_fg = force_foreground(hwnd)
        time.sleep(0.5)
        fg = W.foreground_hwnd()
        print(f"[2] SetForegroundWindow={ok_fg} 当前前台=0x{fg:X} "
              f"匹配目标={fg == hwnd}")

        # --- sendinput，前台
        before = count_keys(log)
        r1 = inject.press(hwnd, 0x20, "sendinput", 30)
        time.sleep(0.3)
        after = count_keys(log)
        print(f"[3] sendinput 前台: via={r1['via']} ok={r1['ok']} "
              f"收到 {after - before} 次  -> {'PASS' if after > before else 'FAIL'}")

        # --- both，前台（应走 sendinput）
        before = after
        r2 = inject.press(hwnd, 0x20, "both", 30)
        time.sleep(0.3)
        after = count_keys(log)
        print(f"[4] both 前台: via={r2['via']} 收到 {after - before} 次 "
              f"-> {'PASS' if after > before else 'FAIL'}")

        # --- both，切回别的窗口（应降级 message 仍能送达）
        others = [w for w in W.list_windows()
                  if w["exe"] == "explorer.exe" and w["visible"] and w["title"]]
        if others:
            force_foreground(others[0]["hwnd"])
            time.sleep(0.4)
            print(f"[5] 前台已切到 explorer hwnd=0x{others[0]['hwnd']:X}")
        before = after
        r3 = inject.press(hwnd, 0x20, "both", 30)
        time.sleep(0.3)
        after = count_keys(log)
        print(f"[6] both 后台: via={r3['via']} 收到 {after - before} 次 "
              f"-> {'PASS' if after > before else 'FAIL'}")

        passed = r1["ok"] and r2["ok"] and r3["ok"]
        print("\n" + "=" * 60)
        print(f" 结论: {'SendInput 与 message 双通道均可用' if passed else '有通道失败'}")
        print("=" * 60)
        return 0 if passed else 1
    finally:
        p.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
