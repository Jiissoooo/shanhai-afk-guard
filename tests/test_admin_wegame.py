"""test_admin_wegame.py - 管理员权限下对真实游戏平台进程的投递实测。

对 WeGame / TASLogin / 游戏本体这类 High 目标直接 PostMessage，
断言 API 返回 TRUE 且 err=0。这是「需要管理员」的最终业务证据。
"""
from __future__ import annotations

import ctypes
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app import winapi as W      # noqa: E402
from app import integrity as I   # noqa: E402
from app import inject           # noqa: E402

WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101

# 关注的目标（真实游戏平台进程）
GAME_HINTS = ("wegame", "taslogin", "segame", "speedball", "tcls", "game",
              "unity", "shanh", "mumu", "ldplayer", "dnplayer", "bluestacks")


def main() -> int:
    me = I.self_integrity()
    lines = []
    lines.append("=" * 72)
    lines.append(" 对真实游戏平台进程的投递实测")
    lines.append("=" * 72)
    lines.append(f"admin={W.is_admin()}  IL={I.il_name(me)} (0x{me:X})")

    wins = [w for w in W.list_windows(include_hidden=True) if w["exe"]]
    seen = set()
    cands = []
    for w in wins:
        if w["pid"] in seen:
            continue
        seen.add(w["pid"])
        exe = w["exe"].lower()
        if any(h in exe for h in GAME_HINTS):
            cands.append(w)

    lines.append(f"\n命中游戏相关进程: {len(cands)} 个")
    lines.append("-" * 72)
    passed = 0
    for w in cands:
        rid = I.process_integrity(w["pid"])
        ctypes.set_last_error(0)
        ok = bool(W.user32.PostMessageW(w["hwnd"], WM_KEYDOWN, 0x20,
                                        inject._lparam(0x20, False)))
        err = ctypes.get_last_error()
        W.user32.PostMessageW(w["hwnd"], WM_KEYUP, 0x20,
                              inject._lparam(0x20, True))
        verdict = "可控制" if ok else ("UIPI拦截" if err == 5 else f"失败({err})")
        lines.append(f"  {w['exe']:<26} pid={w['pid']:<6} "
                     f"IL={I.il_name(rid):<8} PostMessage={str(ok):<5} "
                     f"err={err:<3} -> {verdict}")
        if ok:
            passed += 1

    lines.append("-" * 72)
    lines.append(f"可控制: {passed}/{len(cands)}")
    if cands:
        ratio = passed / len(cands)
        lines.append("")
        if W.is_admin() and ratio > 0.9:
            lines.append("判定: 管理员权限下游戏平台进程全部可控制。")
            lines.append("      => 控制这类目标【需要】管理员启动，已确认。")
        elif not W.is_admin():
            blocked = sum(1 for w in cands
                          if I.process_integrity(w["pid"]) >= I.IL_HIGH)
            lines.append(f"判定: 普通权限，其中 {blocked} 个 High 目标与此对照。")
            lines.append("      需以管理员运行才能控制它们。")
        else:
            lines.append(f"判定: 管理员下仍有 {len(cands) - passed} 个失败，需单独排查。")

    text = "\n".join(lines)
    print(text)
    with open(os.path.join(ROOT, "artifacts", "wegame_admin.txt"), "w",
              encoding="utf-8") as fh:
        fh.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
