"""test_multiopen_pick.py - 多开场景下的下拉选择精度测试。

问题：同一进程（如 山海寻灵.exe）开 3 个号，按 exe 匹配会把启动器的
其它窗口一起接管。选程序后应自动提取公共标题前缀收窄匹配。

本测试启动 3 个标题相近的假窗口（SH_MOPICK_1/2/3），验证：
  1) 下拉框把它们聚合成 1 个程序项，标注 [3个窗口]
  2) 选中后自动提取公共前缀 "SH_MOPICK" 填入标题框
  3) 匹配数正好是 3，不多不少
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

CFG = os.path.join(ROOT, "config", "test_mopick.json")


def check(label, cond, extra=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label} {extra}")
    return cond


def main() -> int:
    print("=" * 72)
    print(" 多开场景下拉选择精度测试")
    print("=" * 72)
    ok = True
    if os.path.exists(CFG):
        os.remove(CFG)

    procs, root = [], None
    try:
        logdir = os.path.join(ROOT, "artifacts")
        os.makedirs(logdir, exist_ok=True)
        names = ["SH_MOPICK_1", "SH_MOPICK_2", "SH_MOPICK_3"]
        for i, nm in enumerate(names):
            log = os.path.join(logdir, f"mopick_{i}.log")
            if os.path.exists(log):
                os.remove(log)
            procs.append(subprocess.Popen(
                [sys.executable, os.path.join(HERE, "probe_target.py"),
                 nm, log, "minimize"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            time.sleep(0.5)

        deadline = time.time() + 10
        while time.time() < deadline:
            got = W.find_windows(title_sub="SH_MOPICK")
            if len(got) >= 3:
                break
            time.sleep(0.15)
        got = W.find_windows(title_sub="SH_MOPICK")
        print(f"\n[1] 假窗口就绪: {len(got)} 个")
        for w in got:
            print(f"      {w['title']:<20} pid={w['pid']} min={w['minimized']}")
        ok &= check("3 个窗口就绪", len(got) == 3, f"({len(got)})")

        # --- 聚合检查
        print("\n[2] 下拉框聚合")
        eng = Engine(CFG)
        eng.targets = [Target(name="多开测试")]
        root = tk.Tk()
        app = App(root, eng)
        root.update()
        app.refresh_app_list()
        root.update()

        py_app = None
        for a in app._app_list:
            if a["exe"].lower().startswith("python"):
                py_app = a
        if py_app:
            print(f"      python.exe 聚合窗口数 = {py_app['windows']}")
            print(f"      标题样本 = {py_app['titles']}")
            ok &= check("聚合到 3+ 个窗口", py_app["windows"] >= 3,
                        f"({py_app['windows']})")
            disp = None
            for d, e in app._app_map.items():
                if e == py_app["exe"]:
                    disp = d
                    break
            print(f"      显示文本 = {disp!r}")
            # 窗口数标记格式为 [N个窗口]
            import re as _re
            ok &= check("显示文本带多开标记",
                        bool(_re.search(r"\[\d+个窗口\]", disp or "")),
                        f"({disp})")
        else:
            ok &= check("找到 python 程序项", False)

        # --- 公共前缀提取
        print("\n[3] 公共标题前缀提取")
        cases = [
            (["SH_MOPICK_1", "SH_MOPICK_2", "SH_MOPICK_3"], "SH_MOPICK"),
            (["山海寻灵 - 主号", "山海寻灵 - 小号"], "山海寻灵"),
            (["A", "B"], ""),
            (["游戏"], ""),
            (["Game - 1", "Game - 2"], "Game"),
        ]
        for titles, expect in cases:
            got_prefix = app._common_title(titles)
            ok &= check(f"{titles} -> {expect!r}",
                        got_prefix == expect, f"(got {got_prefix!r})")

        # --- 选中后的匹配精度
        print("\n[4] 选中后的匹配精度")
        if py_app:
            disp = None
            for d, e in app._app_map.items():
                if e == py_app["exe"]:
                    disp = d
                    break
            app.v_app.set(disp or "")
            app._on_app_pick()
            root.update()
            print(f"      v_exe   = {app.v_exe.get()!r}")
            print(f"      v_title = {app.v_title.get()!r}")
            # 界面实际用的是 AND 语义，测试必须一致
            hits = W.find_windows(app.v_title.get().strip(),
                                  app.v_exe.get().strip(),
                                  include_hidden=True, match_all=True)
            print(f"      实际匹配（AND）= {len(hits)} 个窗口")
            for h in hits:
                print(f"        - {h['title']}")
            ok &= check("匹配数等于 3（不含其它 python 窗口）",
                        len(hits) == 3, f"({len(hits)})")
            ok &= check("标题框被自动填充", app.v_title.get().strip() != "")

            # 额外验证：OR 语义会多命中，证明 AND 收窄确实有必要
            or_hits = W.find_windows(app.v_title.get().strip(),
                                     app.v_exe.get().strip(),
                                     include_hidden=True, match_all=False)
            print(f"      对照 OR 模式命中 = {len(or_hits)} 个")
            ok &= check("AND 比 OR 更精确", len(hits) <= len(or_hits),
                        f"({len(hits)} vs {len(or_hits)})")

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
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
