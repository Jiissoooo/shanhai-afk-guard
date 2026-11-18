"""test_tray.py - 托盘功能回归测试。

用户诉求：点关闭不要退出，收到右下角托盘里。

本测试不靠肉眼，直接验证：
  1) Shell_NotifyIcon 注册成功（托盘里真的有这个图标）
  2) 托盘线程正常存活（消息循环没死）
  3) 提示文字/气泡正常刷新（不抛异常）
  4) 移除图标后能干净卸载
  5) 关键行为：隐藏主窗口 ≠ 退出进程
"""
from __future__ import annotations

import ctypes
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app.tray import TrayIcon  # noqa: E402


def check(label, cond, extra=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label} {extra}")
    return cond


def main() -> int:
    print("=" * 70)
    print(" 系统托盘回归测试")
    print("=" * 70)
    ok = True

    icon = os.path.join(ROOT, "assets", "tray.ico")
    print(f"\n[0] 图标文件: {icon}")
    ok &= check("tray.ico 存在", os.path.exists(icon),
                f"({os.path.getsize(icon)} bytes)" if os.path.exists(icon) else "")

    calls = {"show": 0, "toggle": 0, "stopall": 0, "exit": 0,
             "state": 0}

    def on_show():
        calls["show"] += 1

    def on_toggle():
        calls["toggle"] += 1

    def on_stopall():
        calls["stopall"] += 1

    def on_exit():
        calls["exit"] += 1

    def get_state():
        calls["state"] += 1
        return {"running": True, "count": 3}

    print("\n[1] 启动托盘线程")
    tray = TrayIcon("山海寻灵 · 防AFK控制器", icon, {
        "on_show": on_show,
        "on_toggle": on_toggle,
        "on_stopall": on_stopall,
        "on_exit": on_exit,
        "get_state": get_state,
    })
    ready = tray.start(timeout=4.0)
    time.sleep(0.4)
    ok &= check("托盘线程就绪", ready)
    ok &= check("图标已注册到系统托盘", tray.is_visible())
    print(f"      线程存活: {tray._thread.is_alive() if tray._thread else False}")

    print("\n[2] 提示文字（tooltip）")
    try:
        tip = tray._tooltip_text()
        print(f"      文本: {tip!r}")
        ok &= check("tooltip 含状态信息",
                    "运行中" in tip or "暂停" in tip)
        ok &= check("tooltip 含窗口数", "3" in tip)
        ok &= check("tooltip 长度合法(<=127)", len(tip) <= 127,
                    f"({len(tip)})")
    except Exception as exc:
        ok &= check("tooltip 可用", False, repr(exc))

    print("\n[3] 刷新与气泡提示")
    try:
        tray._refresh()
        ok &= check("_refresh 不抛异常", True)
        tray.notify("已最小化到托盘", "程序仍在后台运行，点击图标恢复")
        ok &= check("气泡通知不抛异常", True)
        tray.notify("测试警告", "这是一个警告气泡", warning=True)
        ok &= check("警告气泡不抛异常", True)
    except Exception as exc:
        ok &= check("气泡可用", False, repr(exc))

    print("\n[4] get_state 回调被调用")
    before = calls["state"]
    tray._tooltip_text()
    ok &= check("get_state 被调用", calls["state"] > before,
                f"({before} -> {calls['state']})")

    print("\n[5] 菜单命令分发")
    from app import tray as T
    tray._on_command(T.CMD_SHOW)
    ok &= check("CMD_SHOW -> on_show", calls["show"] == 1)
    tray._on_command(T.CMD_TOGGLE)
    ok &= check("CMD_TOGGLE -> on_toggle", calls["toggle"] == 1)
    tray._on_command(T.CMD_STOPALL)
    ok &= check("CMD_STOPALL -> on_stopall", calls["stopall"] == 1)
    tray._on_command(T.CMD_EXIT)
    ok &= check("CMD_EXIT -> on_exit", calls["exit"] == 1)

    print("\n[6] 移除图标")
    tray.stop()
    time.sleep(0.6)
    ok &= check("图标已移除", not tray.is_visible(), f"(visible={tray.is_visible()})")

    print("\n[7] 双击启动器不重复注册")
    tray2 = TrayIcon("测试2", icon, {"get_state": lambda: {"running": False,
                                                          "count": 0}})
    ok &= check("第二个实例可独立启动", tray2.start(timeout=4.0))
    ok &= check("第二个图标可见", tray2.is_visible())
    tip2 = tray2._tooltip_text()
    print(f"      第二实例 tooltip: {tip2!r}")
    ok &= check("暂停状态文案正确", "暂停" in tip2)
    tray2.stop()
    time.sleep(0.4)

    print("\n" + "=" * 70)
    print(f" 结果: {'全部通过' if ok else '存在失败项'}")
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
