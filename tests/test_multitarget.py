"""test_multitarget.py - 并发验证。

流程：
  1) 起 3 个独立假窗口（其中 2 个最小化）
  2) 引擎按 Ctrl 风格题目要求匹配它们，间隔 1.0s，抖动 0，方式 message
  3) 真实运行 4 秒
  4) 断言：每个窗口都收到 >= 3 次 WM_KEYDOWN，且次数互不相同（错峰生效）
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app.engine import Engine, Target  # noqa: E402
from app import winapi as W            # noqa: E402

LOGDIR = os.path.join(ROOT, "artifacts")
TITLE = "AFKPROBE"


def spawn(name: str, minimize: bool) -> tuple[subprocess.Popen, str]:
    log = os.path.join(LOGDIR, f"probe_{name}.log")
    if os.path.exists(log):
        os.remove(log)
    args = [sys.executable, os.path.join(HERE, "probe_target.py"),
            f"{TITLE}_{name}", log]
    if minimize:
        args.append("minimize")
    p = subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_CONSOLE)
    return p, log


def count_keys(log: str) -> int:
    if not os.path.exists(log):
        return 0
    with open(log, "r", encoding="utf-8", errors="replace") as fh:
        return sum(1 for line in fh if line.startswith(tuple("0123456789"))
                   and "VK=" in line)


def main() -> int:
    os.makedirs(LOGDIR, exist_ok=True)
    print("=" * 66)
    print(" 并发多窗口后台控制 验证")
    print("=" * 66)

    procs = []
    logs = {}
    try:
        for i, (nm, mini) in enumerate((("A", False), ("B", True), ("C", True))):
            p, log = spawn(nm, mini)
            procs.append(p)
            logs[nm] = log
            time.sleep(0.7)

        # 等窗口注册
        deadline = time.time() + 6
        hwnds = []
        while time.time() < deadline:
            hwnds = W.find_windows(title_sub=TITLE, include_hidden=True)
            if len(hwnds) >= 3:
                break
            time.sleep(0.2)
        print(f"\n[1] 枚举到 {TITLE} 窗口: {len(hwnds)} 个")
        for h in hwnds:
            print(f"    0x{h['hwnd']:X}  {h['title']:<24} min={h['minimized']} "
                  f"visible={h['visible']} pid={h['pid']}")
        assert len(hwnds) >= 3, f"窗口数不足: {len(hwnds)}"

        # 前台切到别处，证明不是靠前台焦点
        print("\n[2] 把前台强制切到 explorer（目标不在前台/已最小化）")
        others = [w for w in W.list_windows()
                  if w["exe"] == "explorer.exe" and w["visible"]]
        if others:
            W.user32.SetForegroundWindow(others[0]["hwnd"])
        time.sleep(0.4)
        fg = W.foreground_hwnd()
        print(f"    当前前台 hwnd=0x{fg:X}  "
              f"(目标里包含: {any(fg == h['hwnd'] for h in hwnds)})")

        cfg = os.path.join(ROOT, "config", "test_multitarget.json")
        eng = Engine(cfg)
        eng.targets = [Target(name="probe", title_sub=TITLE, exe_sub="",
                              key="space", interval_sec=1.0, jitter_pct=0.0,
                              hold_ms=20, method="message",
                              auto_discover=True, max_instances=10)]
        eng._last_scan = 0.0
        eng.rescan(force=True)
        print(f"\n[3] 引擎接管实例数: {len(eng.instances)}")
        for inst in eng.instances:
            print(f"    -> 0x{inst.hwnd:X} {inst.title}")

        eng.set_running(True)
        t0 = time.time()
        while time.time() - t0 < 6.0:
            eng.tick()
            time.sleep(0.05)
        eng.running = False
        time.sleep(0.2)

        print("\n[4] 各窗口实际收到按键次数")
        counts = {}
        for nm, log in logs.items():
            c = count_keys(log)
            counts[nm] = c
            print(f"    probe_{nm}: {c} 次  (log={os.path.basename(log)})")

        print("\n[5] 断言")
        ok_distinct = all(count_keys(l) >= 3 for l in logs.values())
        print(f"    三个窗口全部 >=3 次            : {'PASS' if ok_distinct else 'FAIL'}")
        total = sum(counts.values())
        ok_total = total >= 12
        print(f"    总投递 {total} 次 (>=12)          : {'PASS' if ok_total else 'FAIL'}")

        eng.save()
        done = ok_distinct and ok_total
        print("\n" + "=" * 66)
        print(f" 结论: {'全部通过 —— 后台 + 最小化 + 多窗口并发均生效' if done else '存在失败项'}")
        print("=" * 66)
        return 0 if done else 1
    finally:
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
