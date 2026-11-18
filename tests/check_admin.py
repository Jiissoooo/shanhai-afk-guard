"""check_admin.py - 实测：本机当前所有窗口的完整性级别，以及需不需要管理员。

同时做 A/B 对照：普通权限 vs 管理员权限下能否打开目标进程 token。
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app import winapi as W      # noqa: E402
from app import integrity as I   # noqa: E402


def main() -> int:
    print("=" * 76)
    print(" 管理员权限需求实测")
    print("=" * 76)
    me = I.self_integrity()
    print(f"当前进程 PID       : {os.getpid()}")
    print(f"IsUserAnAdmin()    : {W.is_admin()}")
    print(f"本进程完整性级别    : {I.il_name(me)} (0x{me:X})")

    wins = [w for w in W.list_windows(include_hidden=True) if w["exe"]]
    seen = {}
    for w in wins:
        seen.setdefault(w["exe"], w)

    print(f"\n本机可见进程窗口   : {len(wins)} 个 / {len(seen)} 个不同 exe")
    print("\n" + "-" * 76)
    print(f"{'进程':<28} {'PID':>7} {'完整性':<18} {'可投递':<8}")
    print("-" * 76)

    rows = []
    for exe, w in sorted(seen.items(), key=lambda kv: kv[0].lower()):
        rid = I.process_integrity(w["pid"])
        ok, reason = I.can_target(me, rid)
        rows.append((exe, w["pid"], rid, ok, reason))
        flag = "YES" if ok else "NO"
        print(f"{exe[:27]:<28} {w['pid']:>7} {I.il_name(rid):<18} {flag:<8}")

    print("-" * 76)
    blocked = [r for r in rows if not r[3]]
    print(f"\n汇总: {len(rows) - len(blocked)}/{len(rows)} 个进程可直接投递")
    if blocked:
        print(f"\n需要管理员才能控制的目标 ({len(blocked)} 个):")
        for exe, pid, rid, _ok, reason in blocked:
            print(f"  - {exe} (pid={pid}) IL={I.il_name(rid)}")
            print(f"    {reason}")
    else:
        print("\n本机所有带窗口的进程都不高于本工具 IL，普通权限即可全部控制。")

    # 关键 A/B：能否 OpenProcess 读 token 本身就说明权限差
    print("\n" + "=" * 76)
    print(" 结论")
    print("=" * 76)
    if W.is_admin():
        print(" 当前已是管理员权限。")
        print(" 建议：保持管理员启动，这样高完整性目标也可控，且无需为每个游戏单独判断。")
    elif blocked:
        print(" 当前是普通权限，且存在高完整性目标 -> 需要管理员启动才能控制它们。")
    else:
        print(" 当前是普通权限，本机目标都可控 -> 日常使用不必管理员启动。")
        print(" 但若以后运行了以管理员身份启动的游戏/模拟器，届时需改用管理员启动本工具。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
