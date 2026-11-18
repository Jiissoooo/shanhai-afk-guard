"""test_config.py - 配置层回归。

覆盖：
  1) 默认配置生成 -> 落盘 -> 重新载入（往返一致）
  2) 非法按键被拒绝
  3) 空匹配规则不会误接管全系统窗口（重要：防止一开就乱按键）
  4) 多任务、不同间隔、不同按键互不干扰
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app.engine import Engine, Target  # noqa: E402
from app import winapi as W            # noqa: E402

CFG = os.path.join(ROOT, "config", "test_config.json")


def check(label: str, cond: bool, extra: str = "") -> bool:
    print(f"    [{'PASS' if cond else 'FAIL'}] {label} {extra}")
    return cond


def main() -> int:
    print("=" * 66)
    print(" 配置层回归")
    print("=" * 66)
    ok = True

    if os.path.exists(CFG):
        os.remove(CFG)

    # 1) 往返
    print("\n[1] 配置往返")
    e1 = Engine(CFG)
    e1.targets = [
        Target(name="主号", exe_sub="Game.exe", key="space",
               interval_sec=180, jitter_pct=8, method="message"),
        Target(name="小号", title_sub="山海", key="f5",
               interval_sec=95.5, jitter_pct=0, method="focus"),
    ]
    e1.save()
    e2 = Engine(CFG)
    ok &= check("任务数一致", len(e2.targets) == 2, f"({len(e2.targets)})")
    ok &= check("浮点间隔保留", abs(e2.targets[1].interval_sec - 95.5) < 1e-9)
    ok &= check("方式保留", e2.targets[1].method == "focus")
    ok &= check("按键保留", e2.targets[1].key == "f5")
    ok &= check("中文名保留", e2.targets[0].name == "主号")

    # 2) 非法按键
    print("\n[2] 非法按键拒绝")
    bad = Target(name="x", key="不存在的键")
    try:
        bad.vk()
        ok &= check("应拒绝非法按键", False)
    except ValueError:
        ok &= check("拒绝非法按键", True)
    try:
        W.vk_from_name("f13")
        ok &= check("F13 应可解析(VK 0x7C)", W.vk_from_name("f13") == 0x7C)
    except ValueError:
        ok &= check("F13 应可解析", False)

    # 3) 空规则安全
    print("\n[3] 空规则安全性")
    empty_hits = W.find_windows("", "")
    ok &= check("空规则匹配 0 窗口", len(empty_hits) == 0, f"({len(empty_hits)})")
    e3 = Engine(CFG)
    e3.targets = [Target(name="空规则", title_sub="", exe_sub="")]
    e3._last_scan = 0
    e3.rescan(force=True)
    ok &= check("空规则不接管任何窗口", len(e3.instances) == 0, f"({len(e3.instances)})")

    # 4) 无效窗口不崩
    print("\n[4] 野句柄容错")
    from app import inject
    r = inject.press(0xDEAD0000 & 0x7FFFFFFF, 0x20, "both", 5)
    ok &= check("无效 hwnd 返回 ok=False 而非异常", r["ok"] is False, f"via={r['via']}")

    # 5) 引擎 tick 在无任务时不崩
    print("\n[5] 空引擎 tick")
    e4 = Engine(CFG)
    e4.targets = []
    e4._last_scan = 0
    try:
        for _ in range(5):
            e4.tick()
            time.sleep(0.02)
        ok &= check("空任务 tick 稳定", True)
    except Exception as exc:
        ok &= check("空任务 tick 稳定", False, repr(exc))

    # 6) 大小写不敏感匹配
    print("\n[6] 匹配大小写")
    # 用一个真实主窗口作样本：explorer 的窗口多为隐藏辅助窗，会被 real_only 过滤
    wins = W.list_windows()
    sample = next((w for w in wins if w["exe"] and W.is_real_app_window(w)), None)
    if sample:
        up = W.find_windows(exe_sub=sample["exe"].upper())
        lo = W.find_windows(exe_sub=sample["exe"].lower())
        ok &= check(f"大写/小写都命中 {sample['exe']}",
                    len(up) >= 1 and len(lo) >= 1, f"({len(up)}/{len(lo)})")
        nosuf = W.find_windows(exe_sub=sample["exe"].rsplit(".", 1)[0])
        ok &= check("省略 .exe 后缀也能命中", len(nosuf) >= 1, f"({len(nosuf)})")
        # real_only=False 时应能拿到更多（含辅助窗），证明过滤开关有效
        all_w = W.find_windows(exe_sub=sample["exe"], real_only=False)
        ok &= check("real_only=False 返回数量 >= real_only=True",
                    len(all_w) >= len(up), f"({len(all_w)} vs {len(up)})")
    else:
        ok &= check("窗口样本可用", False)

    print("\n" + "=" * 66)
    print(f" 结果: {'全部通过' if ok else '存在失败项'}")
    print("=" * 66)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
