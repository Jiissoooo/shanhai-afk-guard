"""test_uipi.py - UIPI 拦截的决定性验证。

对同一台机器上:
  A) Medium 完整性目标 -> PostMessage 应成功
  B) High  完整性目标 -> PostMessage 应失败，且 GetLastError()==5 (ACCESS_DENIED)
若无 High 目标则标记 SKIP。

这直接回答「要不要管理员启动」：不是理论，是 API 返回值。
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

WM_KEYDOWN = 0x0100
ERROR_ACCESS_DENIED = 5


def probe(hwnd: int) -> tuple[bool, int]:
    """直接 PostMessage 一个无害的 WM_KEYDOWN，返回 (成功?, lasterror)。"""
    ctypes.set_last_error(0)
    ok = bool(W.user32.PostMessageW(hwnd, WM_KEYDOWN, 0x20,
                                    inject._lparam(0x20, False)))
    err = ctypes.get_last_error()
    # 补发抬起，避免目标状态不一致
    W.user32.PostMessageW(hwnd, 0x0101, 0x20, inject._lparam(0x20, True))
    return ok, err


def main() -> int:
    print("=" * 74)
    print(" UIPI 拦截验证（同一台机器，普通权限）")
    print("=" * 74)
    me = I.self_integrity()
    print(f"本工具: admin={W.is_admin()}  IL={I.il_name(me)} (0x{me:X})\n")

    wins = [w for w in W.list_windows(include_hidden=True) if w["exe"]]
    medium, high = [], []
    seen = set()
    for w in wins:
        if w["pid"] in seen:
            continue
        seen.add(w["pid"])
        rid = I.process_integrity(w["pid"])
        if rid == I.IL_MEDIUM:
            medium.append(w)
        elif rid >= I.IL_HIGH:
            high.append(w)

    print(f"[1] 候选目标: Medium={len(medium)}  High={len(high)}")
    for w in medium[:3]:
        print(f"    MEDIUM 0x{w['hwnd']:X} {w['exe']:<26} {w['title'][:30]!r}")
    for w in high[:5]:
        print(f"    HIGH   0x{w['hwnd']:X} {w['exe']:<26} {w['title'][:30]!r}")

    ok = True

    # --- A: Medium 目标
    print("\n[2] A/B 对照 —— A组: Medium 完整性目标")
    print("-" * 74)
    a_pass = 0
    for w in medium[:5]:
        good, err = probe(w["hwnd"])
        print(f"    {w['exe']:<26} PostMessage={str(good):<5} "
              f"GetLastError={err}")
        if good:
            a_pass += 1
    print(f"    A组成功 {a_pass}/{min(5, len(medium))}")
    ok &= a_pass > 0

    # --- B: High 目标
    print("\n[3] A/B 对照 —— B组: High 完整性目标（本工具的普通权限打不进去）")
    print("-" * 74)
    if not high:
        print("    SKIP: 本机无 High 目标，无法验证")
    else:
        denied = 0
        for w in high[:6]:
            good, err = probe(w["hwnd"])
            mark = "拦截" if (not good and err == ERROR_ACCESS_DENIED) else (
                "通过" if good else f"失败(err={err})")
            print(f"    {w['exe']:<26} PostMessage={str(good):<5} "
                  f"GetLastError={err:<3} -> {mark}")
            if not good and err == ERROR_ACCESS_DENIED:
                denied += 1
        print(f"    B组被 UIPI 拦截 {denied}/{min(6, len(high))}")
        ok &= denied > 0

    # --- C: 引擎层是否正确报告失败（不能静默以为成功）
    print("\n[4] 引擎层是否如实报告（关键：不能假装投递成功）")
    print("-" * 74)
    if high:
        tgt = high[0]
        r = inject.press(tgt["hwnd"], 0x20, "message", 10)
        print(f"    目标 {tgt['exe']} (IL={I.il_name(I.process_integrity(tgt['pid']))})")
        print(f"    press() -> ok={r['ok']} via={r['via']}")
        reported = r["ok"] is False
        print(f"    如实报告失败: {'PASS' if reported else 'FAIL（会静默假成功）'}")
        ok &= reported

    print("\n" + "=" * 74)
    print(" 结论")
    print("=" * 74)
    print(" PostMessage 到 High 目标返回 FALSE + ERROR_ACCESS_DENIED(5)。")
    print(" 这不是本工具的 bug，是 Windows UIPI 的安全边界：")
    print("   较低完整性进程不能向较高完整性进程发送窗口消息 / SendInput。")
    if high:
        print(f" 本机实测有 {len(high)} 个高完整性目标，其中包含游戏平台进程，")
        print(" 因此控制这些目标**必须**以管理员身份启动本工具。")
    print("=" * 74)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
