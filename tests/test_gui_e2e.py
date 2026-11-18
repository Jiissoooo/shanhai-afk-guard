"""test_gui_e2e.py - 界面端到端联调。

不靠肉眼：用 tkinter 直接驱动 App 实例，注入一个真实假窗口，
点「启动」，跑 5 秒，然后断言引擎状态、实例表内容、日志都正确。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app.engine import Engine, Target  # noqa: E402
from app.ui import App                 # noqa: E402
from app import winapi as W            # noqa: E402

LOGDIR = os.path.join(ROOT, "artifacts")
CFG = os.path.join(ROOT, "config", "test_gui_e2e.json")


def main() -> int:
    os.makedirs(LOGDIR, exist_ok=True)
    print("=" * 66)
    print(" 界面端到端联调")
    print("=" * 66)

    log = os.path.join(LOGDIR, "gui_probe.log")
    if os.path.exists(log):
        os.remove(log)
    proc = subprocess.Popen([sys.executable, os.path.join(HERE, "probe_target.py"),
                             "SH_GUI_E2E", log, "minimize"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    ok = True
    try:
        deadline = time.time() + 8
        wins = []
        while time.time() < deadline:
            wins = W.find_windows(title_sub="SH_GUI_E2E", include_hidden=True)
            if wins:
                break
            time.sleep(0.2)
        print(f"\n[1] 目标窗口: {len(wins)} 个 -> "
              f"{wins[0]['title'] if wins else 'NONE'} (min={wins[0]['minimized'] if wins else '-'})")
        if not wins:
            return 1

        if os.path.exists(CFG):
            os.remove(CFG)
        eng = Engine(CFG)
        eng.targets = [Target(name="E2E", title_sub="SH_GUI_E2E",
                              key="space", interval_sec=1.0, jitter_pct=0,
                              hold_ms=15, method="message")]

        root = tk.Tk()
        app = App(root, eng)

        # 模拟点选第一行 + 点启动
        root.update()
        children = app.tree.get_children()
        print(f"\n[2] 界面任务行数: {len(children)}")
        ok &= len(children) == 1
        if children:
            app.tree.selection_set(children[0])
            root.update()
            print(f"    表单载入: name={app.v_name.get()!r} "
                  f"title={app.v_title.get()!r} key={app.v_key.get()!r}")

        eng.rescan(force=True)
        app.toggle_run()
        root.update()
        print(f"\n[3] 点启动后 engine.running={eng.running} "
              f"按钮文字={app.btn_run.cget('text')!r}")
        ok &= eng.running is True
        ok &= "暂停" in app.btn_run.cget("text")

        # 跑 5 秒，期间持续泵事件
        t0 = time.time()
        while time.time() - t0 < 5.0:
            root.update()
            time.sleep(0.04)

        rows = app.itree.get_children()
        print(f"\n[4] 实例表行数: {len(rows)}")
        for r in rows:
            vals = app.itree.item(r, "values")
            print(f"    {vals}")
        ok &= len(rows) >= 1

        with open(log, encoding="utf-8") as fh:
            hits = sum(1 for ln in fh if ln.startswith(tuple("0123456789")) and "VK=" in ln)
        print(f"\n[5] 目标实际收到按键: {hits} 次")
        ok &= hits >= 3

        logtext = app.log_txt.get("1.0", "end")
        has_takeover = "接管窗口" in logtext
        print(f"[6] 日志含接管记录: {has_takeover}")
        for ln in logtext.strip().splitlines()[:5]:
            print(f"    | {ln}")
        ok &= has_takeover

        # 点暂停
        app.toggle_run()
        root.update()
        print(f"\n[7] 点暂停后 running={eng.running} 按钮={app.btn_run.cget('text')!r}")
        ok &= eng.running is False

        eng.shutdown()
        root.destroy()

        print("\n" + "=" * 66)
        print(f" 结论: {'界面全流程通过' if ok else '存在失败项'}")
        print("=" * 66)
        return 0 if ok else 1
    finally:
        proc.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
