"""test_foreground.py - 抢前台回归测试（正式套件）。

保留开发期发现的真实 bug 作为回归：
  已可见且未最小化的窗口，若只做 AttachThreadInput + SetForegroundWindow，
  会稳定失败(0/6)。必须制造一次状态变更(SW_MINIMIZE -> SW_RESTORE)。
本测试锁死四种窗口初始状态都必须是满成功率。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app import winapi as W  # noqa: E402
from app import inject        # noqa: E402

TRIES = 5


def spawn(name: str, minimize: bool):
    log = os.path.join(ROOT, "artifacts", f"fgt_{name}.log")
    if os.path.exists(log):
        os.remove(log)
    args = [sys.executable, os.path.join(HERE, "probe_target.py"),
            f"SH_FGT_{name}", log]
    if minimize:
        args.append("minimize")
    p = subprocess.Popen(args, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    deadline = time.time() + 8
    while time.time() < deadline:
        wins = W.find_windows(title_sub=f"SH_FGT_{name}")
        if wins:
            return p, wins[0]
        time.sleep(0.1)
    return p, None


def park():
    others = [w for w in W.list_windows()
              if w["exe"] == "explorer.exe" and w["visible"] and w["title"]]
    if others:
        inject.force_foreground(others[0]["hwnd"])
    time.sleep(0.06)


def measure(hwnd) -> int:
    ok = 0
    for _ in range(TRIES):
        park()
        if inject.force_foreground(hwnd):
            ok += 1
        time.sleep(0.06)
    return ok


def main() -> int:
    print("=" * 68)
    print(" 抢前台回归（四种窗口初始状态）")
    print("=" * 68)
    procs, results = [], {}
    try:
        for label, mini in (("A可见", False), ("B最小化", True),
                            ("C可见+激活", False), ("D最小化+激活", True)):
            p, w = spawn(label, mini)
            procs.append(p)
            if not w:
                print(f"  {label:<14} 窗口创建失败")
                results[label] = 0
                continue
            if "激活" in label:
                inject.force_foreground(w["hwnd"])
                time.sleep(0.2)
            results[label] = measure(w["hwnd"])
            bar = "#" * results[label] + "." * (TRIES - results[label])
            print(f"  {label:<14} {results[label]}/{TRIES}  [{bar}]")

        print("-" * 68)
        allok = all(v == TRIES for v in results.values())
        for k, v in results.items():
            print(f"  {'PASS' if v == TRIES else 'FAIL'}  {k} ({v}/{TRIES})")
        print("=" * 68)
        print(f" 结论: {'四种初始状态均满成功率' if allok else '存在失败状态'}")
        print("=" * 68)
        return 0 if allok else 1
    finally:
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
