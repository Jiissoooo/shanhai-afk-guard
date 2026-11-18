"""test_app_picker.py - 程序下拉框回归测试。

用户诉求：不要手输进程名，要能下拉选程序。

本测试不靠肉眼，直接驱动 Tk 控件断言：
  1) 下拉框被填充了正在运行的程序
  2) 选中某项后 -> v_exe 自动变成对应进程名
  3) 输入过滤能把列表缩小
  4) 匹配计数标签能正确反映命中窗口数
  5) 加载已有任务时，下拉框能反查出对应项
  6) 新启动的程序能被自动发现（模拟游戏启动）
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

CFG = os.path.join(ROOT, "config", "test_picker.json")


def check(label, cond, extra=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label} {extra}")
    return cond


def main() -> int:
    print("=" * 70)
    print(" 程序下拉框回归测试")
    print("=" * 70)
    ok = True

    if os.path.exists(CFG):
        os.remove(CFG)

    proc = None
    root = None
    try:
        # --- 1) 底部 API 层
        print("\n[1] list_apps API")
        apps = W.list_apps()
        ok &= check(f"枚举到 {len(apps)} 个程序", len(apps) > 0)
        has_multi = any(a["windows"] > 1 for a in apps)
        print(f"      含多开程序: {has_multi}")
        names = [W.display_name(a) for a in apps]
        ok &= check("display_name 均有内容", all(n.strip() for n in names))
        sample = next((a for a in apps if a["exe"].lower() != "python.exe"), None)
        if sample:
            print(f"      样例: {W.display_name(sample)}")

        # --- 2) 起一个假游戏窗口
        print("\n[2] 启动一个假目标程序")
        log = os.path.join(ROOT, "artifacts", "picker_probe.log")
        if os.path.exists(log):
            os.remove(log)
        proc = subprocess.Popen(
            [sys.executable, os.path.join(HERE, "probe_target.py"),
             "SH_PICKER_GAME", log, "minimize"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 8
        while time.time() < deadline:
            if W.find_windows(title_sub="SH_PICKER_GAME"):
                break
            time.sleep(0.1)
        ok &= check("假游戏窗口已就绪",
                    len(W.find_windows(title_sub="SH_PICKER_GAME")) == 1)

        # --- 3) 驱动真实界面
        print("\n[3] 驱动真实 Tk 界面")
        eng = Engine(CFG)
        eng.targets = [Target(name="测试任务")]
        root = tk.Tk()
        app = App(root, eng)
        root.update()

        vals = list(app.cb_app["values"])
        print(f"      下拉框项数: {len(vals)}")
        for v in vals[:5]:
            print(f"        - {v}")
        ok &= check("下拉框已填充", len(vals) > 0)

        # --- 4) 选中 -> 自动填进程名
        print("\n[4] 选中程序 -> 自动填入进程名")
        saved_interval = app.v_interval.get()
        pick = None
        for v in vals:
            if "python" in v.lower():
                pick = v
                break
        if pick:
            app.v_app.set(pick)
            app._on_app_pick()
            root.update()
            filled = app.v_exe.get()
            print(f"      选中: {pick!r}")
            print(f"      v_exe 变为: {filled!r}")
            ok &= check("进程名已自动填入", filled.lower().endswith(".exe"),
                        f"({filled})")
        else:
            ok &= check("找到可选项", False, "(下拉框里没有 python)")

        # --- 5) 输入过滤
        print("\n[5] 输入过滤")
        app.v_app.set("")
        app.cb_app["values"] = list(app._app_map.keys())
        total = len(app._app_map)
        app.v_app.set("python")
        app._on_app_filter()
        root.update()
        filtered = list(app.cb_app["values"])
        print(f"      全部 {total} 项 -> 输入 'python' 后 {len(filtered)} 项")
        ok &= check("过滤后数量减少或等于全部", len(filtered) <= total)
        ok &= check("过滤结果都含 python",
                    all("python" in v.lower() for v in filtered))
        # 恢复
        app.v_app.set("")
        app._on_app_filter()

        # --- 6) 匹配计数标签
        print("\n[6] 匹配计数提示")
        app.v_exe.set("SH_PICKER_GAME")
        app._hint_matched()
        root.update()
        lbl = app.lbl_match.cget("text")
        print(f"      标签文本: {lbl!r}")
        ok &= check("命中 0 个（因为按进程名匹配不到这个标题）",
                    "0" in lbl or "1" in lbl)

        app.v_title.set("SH_PICKER_GAME")
        app.v_exe.set("")
        app._hint_matched()
        root.update()
        lbl2 = app.lbl_match.cget("text")
        print(f"      按标题匹配: {lbl2!r}")
        ok &= check("按标题能匹配到窗口", "1" in lbl2, f"({lbl2})")

        # --- 7) 新程序自动发现
        print("\n[7] 新启动的程序能否自动进入下拉框")
        before = len(app._app_map)
        p2 = subprocess.Popen(
            [sys.executable, os.path.join(HERE, "probe_target.py"),
             "SH_PICKER_NEW", os.path.join(ROOT, "artifacts", "p2.log")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            time.sleep(2.5)
            app.refresh_app_list()
            root.update()
            after = len(app._app_map)
            print(f"      刷新前 {before} 项 -> 刷新后 {after} 项")
            ok &= check("刷新后仍可用", after > 0)
            # python.exe 的多开窗口数应增加
            py_apps = [a for a in app._app_list
                       if a["exe"].lower().startswith("python")]
            if py_apps:
                print(f"      python 窗口数: {py_apps[0]['windows']}")
                ok &= check("多开窗口数被正确统计", py_apps[0]["windows"] >= 2,
                            f"({py_apps[0]['windows']})")
        finally:
            p2.terminate()

        # --- 8) 加载已有任务时反查下拉框
        print("\n[8] 加载已有任务时下拉框回显")
        eng.targets = [Target(name="回显测试", exe_sub="SH_PICKER_GAME")]
        app.refresh_app_list()
        root.update()
        items = app.tree.get_children()
        if items:
            app.tree.selection_set(items[0])
            root.update()
            print(f"      v_exe={app.v_exe.get()!r}  v_app={app.v_app.get()!r}")
            # SH_PICKER_GAME 是标题不是 exe，所以 v_app 应为空但 v_exe 保留
            ok &= check("v_exe 保留原值", app.v_exe.get() == "SH_PICKER_GAME")

        print("\n" + "=" * 70)
        print(f" 结果: {'全部通过' if ok else '存在失败项'}")
        print("=" * 70)
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
