"""test_tray_e2e.py - 「点关闭收进托盘」端到端测试。

用户明确诉求：点关闭不要退出，收到右下角托盘里，后台继续工作。

本测试驱动真实 Tk 界面验证：
  1) 点 X 后窗口隐藏（withdraw），但进程仍活着、引擎仍在跑
  2) 托盘图标仍然可见
  3) 托盘「打开主窗口」能恢复窗口
  4) 托盘「启动/暂停」能控制引擎（不用切回窗口）
  5) 托盘「退出程序」才真退出
  6) 窗口隐藏期间引擎 tick 仍在推进（后台真的在干活）
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

CFG = os.path.join(ROOT, "config", "test_tray_e2e.json")


def check(label, cond, extra=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label} {extra}")
    return cond


def count_keys(log):
    if not os.path.exists(log):
        return 0
    with open(log, encoding="utf-8", errors="replace") as fh:
        return sum(1 for ln in fh
                   if ln.startswith(tuple("0123456789")) and "VK=" in ln)


def main() -> int:
    print("=" * 72)
    print(" 点关闭收进托盘 · 端到端测试")
    print("=" * 72)
    ok = True
    if os.path.exists(CFG):
        os.remove(CFG)

    proc = None
    root = None
    try:
        # 起一个假游戏，用于验证后台是否真的还在按键
        log = os.path.join(ROOT, "artifacts", "tray_e2e.log")
        if os.path.exists(log):
            os.remove(log)
        proc = subprocess.Popen(
            [sys.executable, os.path.join(HERE, "probe_target.py"),
             "SH_TRAY_E2E", log, "minimize"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 8
        while time.time() < deadline:
            if W.find_windows(title_sub="SH_TRAY_E2E"):
                break
            time.sleep(0.1)

        print("\n[1] 启动界面与托盘")
        eng = Engine(CFG)
        eng.targets = [Target(name="托盘测试", title_sub="SH_TRAY_E2E",
                              key="space", interval_sec=0.6, jitter_pct=0,
                              hold_ms=15, method="message")]
        root = tk.Tk()
        app = App(root, eng)
        root.update()
        time.sleep(0.5)
        root.update()

        ok &= check("托盘图标已创建", app.tray is not None)
        ok &= check("托盘图标可见", bool(app.tray and app.tray.is_visible()))
        ok &= check("默认勾选「关闭时最小化到托盘」", app.var_tray.get() is True)

        # 启动引擎
        eng.set_running(True)
        t0 = time.time()
        while time.time() - t0 < 2.0:
            root.update()
            time.sleep(0.05)
        before_keys = count_keys(log)
        print(f"      隐藏前已投递 {before_keys} 次按键")
        ok &= check("隐藏前引擎在工作", before_keys >= 1)

        print("\n[2] 模拟点击窗口 X（关闭按钮）")
        app.on_close()
        root.update()
        time.sleep(0.3)
        root.update()

        hidden = app.hidden_to_tray
        # Tk withdraw 后 state 为 'withdrawn'
        try:
            state = root.state()
        except Exception:
            state = "?"
        print(f"      hidden_to_tray={hidden}  Tk state={state!r}")
        ok &= check("窗口已隐藏", hidden is True)
        ok &= check("Tk 状态为 withdrawn", state == "withdrawn", f"({state})")
        ok &= check("托盘图标仍可见", bool(app.tray and app.tray.is_visible()))
        ok &= check("引擎仍在运行", eng.running is True)

        print("\n[3] 隐藏后后台是否仍在按键（关键）")
        t0 = time.time()
        while time.time() - t0 < 3.0:
            # 注意：窗口已 withdraw，但仍要 pump 事件，否则 after 回调不跑
            root.update()
            time.sleep(0.05)
        after_keys = count_keys(log)
        print(f"      隐藏后投递累计 {after_keys} 次（增加 {after_keys - before_keys}）")
        ok &= check("隐藏期间引擎继续投递按键",
                    after_keys > before_keys,
                    f"({before_keys} -> {after_keys})")

        print("\n[4] 托盘菜单「启动/暂停」")
        before_running = eng.running
        app._tray_toggle()
        root.update()
        print(f"      running: {before_running} -> {eng.running}")
        ok &= check("托盘能切换引擎状态", eng.running != before_running)
        app._tray_toggle()
        root.update()
        ok &= check("再切一次恢复", eng.running == before_running)

        print("\n[5] 托盘菜单「打开主窗口」")
        app.show_from_tray()
        root.update()
        time.sleep(0.3)
        try:
            state2 = root.state()
        except Exception:
            state2 = "?"
        print(f"      恢复后 Tk state={state2!r}  hidden_to_tray={app.hidden_to_tray}")
        ok &= check("窗口已恢复", state2 == "normal", f"({state2})")
        ok &= check("hidden_to_tray 已复位", app.hidden_to_tray is False)

        print("\n[6] 托盘「退出程序」才真退出")
        app._tray_exit()
        # 退出后进程应结束；此处只验证资源已释放
        ok &= check("_really_quit 置位", app._really_quit is True)
        time.sleep(0.5)
        root = None  # 已 destroy，避免 finally 再操作

        print("\n" + "=" * 72)
        print(f" 结果: {'全部通过' if ok else '存在失败项'}")
        print("=" * 72)
        return 0 if ok else 1
    finally:
        try:
            if root is not None:
                root.destroy()
        except Exception:
            pass
        if proc:
            proc.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
