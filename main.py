"""main.py - 入口。python main.py 直接跑；python main.py --check 只做自检不发按键。"""
from __future__ import annotations

import argparse
import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def self_check() -> int:
    from app import winapi as W
    from app import inject
    from app import integrity
    from app.engine import Target

    print("=" * 62)
    print(" 山海寻灵 · 防AFK控制器  自检")
    print("=" * 62)
    print(f"Python           : {sys.version.split()[0]} ({8*ctypes.sizeof(ctypes.c_void_p)} bit)")
    print(f"管理员权限        : {'是' if W.is_admin() else '否（部分游戏需管理员）'}")

    # 1) VK 映射
    cases = ["space", "enter", "f8", "numpad0", "a", "0x20"]
    print("\n[1] 按键映射")
    ok1 = True
    for c in cases:
        try:
            vk = W.vk_from_name(c)
            sc = W.scan_from_vk(vk)
            print(f"    {c:<10} VK=0x{vk:02X}  SC=0x{sc:02X}  ext={W.is_extended_vk(vk)}")
        except ValueError as exc:
            ok1 = False
            print(f"    {c:<10} 失败: {exc}")

    # 2) 窗口枚举
    print("\n[2] 窗口枚举")
    wins = W.list_windows()
    print(f"    可见顶层窗口: {len(wins)}")
    for w in wins[:6]:
        print(f"    - {w['exe']:<24} pid={w['pid']:<6} {w['title'][:40]!r}")
    ok2 = len(wins) > 0

    # 3) 匹配器 —— 用一个真实主窗口作样本（explorer 的窗口多为隐藏辅助窗，
    #    会被 real_only 过滤掉，不适合当样本）
    print("\n[3] 匹配器")
    sample = None
    for w in wins:
        if W.is_real_app_window(w) and w["exe"]:
            sample = w
            break
    if sample:
        hits = W.find_windows(exe_sub=sample["exe"])
        nosuf = W.find_windows(exe_sub=sample["exe"].rsplit(".", 1)[0])
        print(f"    样本 {sample['exe']} -> 精确匹配 {len(hits)} 个，"
              f"忽略后缀 {len(nosuf)} 个")
        ok3 = len(hits) >= 1 and len(nosuf) >= 1
    else:
        print("    跳过：无真实主窗口样本")
        ok3 = False

    # 4) 配置模型
    print("\n[4] 配置模型")
    t = Target(name="t", key="space", interval_sec=12.5)
    print(f"    Target -> vk=0x{t.vk():02X} interval={t.interval_sec}")
    ok4 = t.vk() == 0x20

    # 5) 注入自检（仅投递消息）。必须挑一个本进程权限足够的目标，
    #    否则 High 完整性目标会被 UIPI 正常拦截（那是正确行为，不是缺陷）。
    print("\n[5] 注入自检（PostMessage 到一个无害窗口）")
    ok5 = False
    me = integrity.self_integrity()
    injectable = None
    for w in wins:
        if not (W.is_real_app_window(w) and w["exe"]):
            continue
        okp, _why = integrity.can_target(me, integrity.process_integrity(w["pid"]))
        if okp:
            injectable = w
            break
    if injectable:
        r = inject.press(injectable["hwnd"], 0x20, "message", 10)
        print(f"    目标 {injectable['exe']} {injectable['title'][:24]!r} "
              f"-> ok={r['ok']} via={r['via']}")
        ok5 = r["ok"]
    else:
        print("    跳过：没有权限足够（IL 不高于本进程）的可注入窗口")

    # 6) 引擎 dry-run
    print("\n[6] 引擎 tick dry-run")
    from app.engine import Engine
    eng = Engine(os.path.join(os.getcwd(), "config", "selftest.json"))
    eng.targets = []
    eng.running = False
    eng.tick()
    print(f"    tick OK, instances={len(eng.instances)}")
    ok6 = True

    print("\n" + "=" * 62)
    results = [ok1, ok2, ok3, ok4, ok5, ok6]
    print(f" 结果: {sum(results)}/{len(results)} 通过")
    print("=" * 62)
    return 0 if all(results) else 1


def _utf8_stdout():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main():
    _utf8_stdout()
    ap = argparse.ArgumentParser(description="山海寻灵 防AFK控制器")
    ap.add_argument("--check", action="store_true", help="只跑自检，不启动界面")
    ap.add_argument("--admin", action="store_true",
                    help="若当前非管理员则自动提权重启")
    ap.add_argument("--permissions", action="store_true",
                    help="打印本机窗口完整性级别与权限需求")
    args = ap.parse_args()
    _dpi_aware()
    if sys.platform != "win32":
        print("仅支持 Windows")
        return 2

    if args.permissions:
        from app import winapi as W
        from app import integrity as I
        from app import elevate as E
        me = I.self_integrity()
        print(f"管理员: {W.is_admin()}  完整性: {I.il_name(me)} (0x{me:X})")
        print(f"状态  : {E.status_line()}")
        blocked = 0
        seen = set()
        for w in W.list_windows(include_hidden=True):
            if not w["exe"] or w["pid"] in seen:
                continue
            seen.add(w["pid"])
            rid = I.process_integrity(w["pid"])
            ok, _ = I.can_target(me, rid)
            if not ok:
                blocked += 1
                print(f"  [需管理员] {w['exe']} (pid={w['pid']}) IL={I.il_name(rid)}")
        print(f"\n需要管理员才能控制的目标: {blocked} 个")
        return 0

    if args.admin:
        from app import elevate as E
        E.ensure_elevated(auto=True)

    if args.check:
        return self_check()
    from app.ui import run
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
