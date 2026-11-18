"""test_window_filter.py - 窗口过滤回归。

真实事故：对 wegame.exe 配置任务时，include_hidden 把它的 16 个内部
辅助窗口（WECHAT_AUTH_MESSAGE_WIN / TCLS_CORE_WND / GDI+ Window /
no_active_wnd / ClassName<数字> ...）全部接管，逐个发按键。

本测试锁死过滤规则：
  1) wegame 这类多窗口程序，过滤后的数量必须远小于过滤前
  2) 过滤结果里不能出现已知的辅助窗口类/标题
  3) 真实的主窗口必须仍能被匹配到（不能过滤过头）
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

JUNK_MARKERS = ("gdi+ window", "no_active_wnd", "classname", "cross_msg",
                "auth_message", "tcls_core", "msctfime", "default ime")


def check(label, cond, extra=""):
    print(f"    [{'PASS' if cond else 'FAIL'}] {label} {extra}")
    return cond


def main() -> int:
    print("=" * 70)
    print(" 窗口过滤回归")
    print("=" * 70)
    ok = True

    # 1) 真实机器上的多窗口程序（找窗口数最多的那个 exe 做样本）
    print("\n[1] 真实多窗口程序的过滤效果")
    raw = W.list_windows(include_hidden=True)
    by_exe = {}
    for w in raw:
        if w["exe"]:
            by_exe.setdefault(w["exe"], []).append(w)
    worst = max(by_exe.items(), key=lambda kv: len(kv[1]))
    exe, wins = worst
    print(f"    样本: {exe}  原始窗口数={len(wins)}")

    filtered = W.find_windows(exe_sub=exe, include_hidden=True)
    real = [w for w in wins if W.is_real_app_window(w)]
    print(f"    过滤后={len(filtered)}  按规则应为={len(real)}")
    ok &= check("过滤后数量与规则一致", len(filtered) == len(real))
    ok &= check(f"过滤掉了辅助窗口 ({len(wins)} -> {len(filtered)})",
                len(filtered) < len(wins) or len(wins) <= 2,
                f"({len(wins)}->{len(filtered)})")

    bad = []
    for w in filtered:
        t = (w["title"] or "").lower()
        c = (w["cls"] or "").lower()
        for m in JUNK_MARKERS:
            if m in t or m in c:
                bad.append(f"{w['title'][:30]!r} cls={w['cls']!r}")
                break
    ok &= check("结果中无已知辅助窗口", not bad, f"({bad[:3]})" if bad else "")

    # 2) 最小化窗口必须仍被接管（后台运行的核心前提，曾因尺寸=0x0 被误杀）
    print("\n[2] 最小化窗口不被误过滤（关键回归）")
    logp = os.path.join(ROOT, "artifacts", "wf_probe.log")
    if os.path.exists(logp):
        os.remove(logp)

    def spawn_probe(title, minimize):
        args = [sys.executable, os.path.join(HERE, "probe_target.py"),
                title, logp]
        if minimize:
            args.append("minimize")
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        deadline = time.time() + 8
        while time.time() < deadline:
            hs = W.find_windows(title_sub=title, real_only=False)
            if hs:
                return proc, hs[0]
            time.sleep(0.1)
        return proc, None

    p1, w_min = spawn_probe("SH_WF_MIN", True)
    try:
        if w_min:
            print(f"    最小化窗口 client={w_min['w']}x{w_min['h']} "
                  f"rect={w_min['rw']}x{w_min['rh']} min={w_min['minimized']}")
            ok &= check("最小化窗口通过过滤",
                        W.is_real_app_window(w_min))
            hits = W.find_windows(title_sub="SH_WF_MIN")
            ok &= check("最小化窗口能被 find_windows 接管",
                        len(hits) == 1, f"({len(hits)})")
            ok &= check("最小化时 rect 尺寸非零",
                        w_min["rw"] > 0 and w_min["rh"] > 0,
                        f"({w_min['rw']}x{w_min['rh']})")
        else:
            ok &= check("最小化 probe 创建", False)
    finally:
        p1.terminate()

    p2, w_norm = spawn_probe("SH_WF_NORM", False)
    try:
        if w_norm:
            ok &= check("正常窗口通过过滤", W.is_real_app_window(w_norm))
            hits = W.find_windows(title_sub="SH_WF_NORM")
            ok &= check("正常窗口能被接管", len(hits) == 1, f"({len(hits)})")
        else:
            ok &= check("正常 probe 创建", False)
    finally:
        p2.terminate()

    # 3) 空规则仍然安全
    print("\n[3] 空规则仍不误接管")
    ok &= check("空规则返回 0", len(W.find_windows("", "")) == 0)

    # 4) 过滤规则单元测试
    print("\n[4] 过滤规则单元验证")
    cases = [
        ({"visible": True, "title": "GDI+ Window (wegame.exe)",
          "cls": "GDI+ Window", "w": 800, "h": 600}, False),
        ({"visible": True, "title": "no_active_wnd", "cls": "no_active_wnd",
          "w": 800, "h": 600}, False),
        ({"visible": True, "title": "ClassName497694437",
          "cls": "ClassName497694437", "w": 800, "h": 600}, False),
        ({"visible": True, "title": "WECHAT_AUTH_MESSAGE_WIN",
          "cls": "Chrome_MessageWindow", "w": 800, "h": 600}, False),
        ({"visible": True, "title": "山海寻灵", "cls": "UnityWndClass",
          "w": 1280, "h": 720}, True),
        ({"visible": True, "title": "", "cls": "UnityWndClass",
          "w": 1280, "h": 720}, False),
        ({"visible": False, "title": "山海寻灵", "cls": "UnityWndClass",
          "w": 1280, "h": 720}, False),
        ({"visible": True, "title": "小条", "cls": "SomeCls",
          "w": 50, "h": 30}, False),
    ]
    for info, expect in cases:
        got = W.is_real_app_window(info)
        ok &= check(f"{info['title'][:26]!r:<30} -> {expect}",
                    got == expect, "" if got == expect else f"(got {got})")

    print("\n" + "=" * 70)
    print(f" 结果: {'全部通过' if ok else '存在失败项'}")
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
