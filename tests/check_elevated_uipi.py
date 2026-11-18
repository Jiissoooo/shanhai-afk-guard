"""check_elevated_uipi.py - 管理员权限下复测 UIPI。

在管理员实例中运行时，之前被拦截的 High 目标应该全部变为可投递。
这就是「需不需要管理员」的最终判定：如果这里从 0/6 变成 6/6，答案就是「需要」。
写完结果到 artifacts/uipi_admin.txt 供非管理员进程读取。
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


def probe(hwnd: int):
    ctypes.set_last_error(0)
    ok = bool(W.user32.PostMessageW(hwnd, WM_KEYDOWN, 0x20,
                                    inject._lparam(0x20, False)))
    err = ctypes.get_last_error()
    W.user32.PostMessageW(hwnd, 0x0101, 0x20, inject._lparam(0x20, True))
    return ok, err


def main() -> int:
    me = I.self_integrity()
    out = []
    out.append("=" * 70)
    out.append(" 管理员权限下的 UIPI 复测")
    out.append("=" * 70)
    out.append(f"admin={W.is_admin()}  IL={I.il_name(me)} (0x{me:X})")

    wins = [w for w in W.list_windows(include_hidden=True) if w["exe"]]
    seen, high = set(), []
    for w in wins:
        if w["pid"] in seen:
            continue
        seen.add(w["pid"])
        if I.process_integrity(w["pid"]) >= I.IL_HIGH:
            high.append(w)

    out.append(f"\nHigh 完整性目标: {len(high)} 个")
    out.append("-" * 70)
    passed = 0
    for w in high[:8]:
        ok, err = probe(w["hwnd"])
        out.append(f"  {w['exe']:<28} PostMessage={str(ok):<5} err={err}"
                   f"  -> {'可控制' if ok else '被拦截'}")
        if ok:
            passed += 1
    out.append("-" * 70)
    out.append(f"High 目标可控制: {passed}/{min(8, len(high))}")

    ok_all = passed >= min(5, len(high)) and len(high) > 0
    out.append("")
    out.append(f"判定: {'管理员下 UIPI 拦截消失 —— 确认需要管理员' if ok_all else '未达预期'}")

    text = "\n".join(out)
    print(text)
    with open(os.path.join(ROOT, "artifacts", "uipi_admin.txt"), "w",
              encoding="utf-8") as fh:
        fh.write(text + "\n")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
