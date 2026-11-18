"""test_run_flow.py - 用户实际操作流程测试：填完信息怎么跑起来。

真实用户路径（最容易卡住的点）：
   新建任务 -> 选程序 -> 填间隔 -> （有没有点保存？）-> 点启动

要验证的关键行为：
  1) 填完信息后**必须先点保存**，否则引擎读到的是旧配置
  2) 点启动后，未保存的修改不会被应用（这是最容易困惑的点）
  3) 保存后点启动，引擎立即接管窗口并开始投递
  4) 运行中改参数并保存，新参数立刻生效
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

CFG = os.path.join(ROOT, "config", "test_runflow.json")


def check(label, cond, extra=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label} {extra}")
    return cond


def count_keys(log):
    if not os.path.exists(log):
        return 0
    with open(log, encoding="utf-8", errors="replace") as fh:
        return sum(1 for ln in fh
                   if ln.startswith(tuple("0123456789")) and "VK=" in ln)


def main() -> int:
    print("=" * 72)
    print(" 填完信息怎么运行 · 操作流程测试")
    print("=" * 72)
    ok = True
    if os.path.exists(CFG):
        os.remove(CFG)

    proc, root = None, None
    try:
        log = os.path.join(ROOT, "artifacts", "runflow.log")
        if os.path.exists(log):
            os.remove(log)
        proc = subprocess.Popen(
            [sys.executable, os.path.join(HERE, "probe_target.py"),
             "SH_RUNFLOW", log, "minimize"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 8
        while time.time() < deadline:
            if W.find_windows(title_sub="SH_RUNFLOW"):
                break
            time.sleep(0.1)
        ok &= check("测试目标窗口就绪",
                    len(W.find_windows(title_sub="SH_RUNFLOW")) == 1)

        eng = Engine(CFG)
        eng.targets = [Target(name="流程测试")]
        root = tk.Tk()
        app = App(root, eng)
        root.update()
        time.sleep(0.3)
        root.update()

        print("\n[1] 在表单里填信息（但还没点保存）")
        rows = app.tree.get_children()
        app.tree.selection_set(rows[0])
        root.update()
        app.v_name.set("山海主号")
        app.v_title.set("SH_RUNFLOW")
        app.v_exe.set("")
        app.v_key.set("space")
        app.v_interval.set("0.8")
        app.v_jitter.set("0")
        app.v_method.set("message")
        root.update()
        print("      表单已填: 名称=山海主号 标题=SH_RUNFLOW 间隔=0.8")

        print("\n[2] 未保存时直接点启动（应自动应用表单）")
        app.toggle_run()
        root.update()
        t0 = time.time()
        while time.time() - t0 < 2.5:
            root.update()
            time.sleep(0.05)
        hits = W.find_windows(eng.targets[0].title_sub,
                              eng.targets[0].exe_sub, include_hidden=True,
                              match_all=True)
        print(f"      引擎里的规则: title={eng.targets[0].title_sub!r} "
              f"exe={eng.targets[0].exe_sub!r}")
        print(f"      匹配窗口数: {len(hits)}")
        # 启动时会自动应用表单，未点保存也能生效（修过的坑）
        ok &= check("启动时自动应用了表单内容",
                    eng.targets[0].title_sub == "SH_RUNFLOW",
                    f"({eng.targets[0].title_sub!r})")
        ok &= check("自动应用后已接管窗口", len(hits) == 1, f"({len(hits)})")
        n_auto = count_keys(log)
        print(f"      自动应用后收到按键: {n_auto} 次")
        ok &= check("未点保存也能真正跑起来", n_auto >= 1, f"({n_auto})")

        print("\n[3] 点「保存」再启动")
        app.save_task()
        root.update()
        print(f"      保存后引擎规则: title={eng.targets[0].title_sub!r}")
        ok &= check("保存后规则已写入引擎",
                    eng.targets[0].title_sub == "SH_RUNFLOW",
                    f"({eng.targets[0].title_sub!r})")
        ok &= check("间隔已写入", abs(eng.targets[0].interval_sec - 0.8) < 1e-6,
                    f"({eng.targets[0].interval_sec})")

        eng.rescan(force=True)
        root.update()
        print(f"      引擎接管实例数: {len(eng.instances)}")
        ok &= check("已接管目标窗口", len(eng.instances) >= 1)

        t0 = time.time()
        while time.time() - t0 < 3.0:
            root.update()
            time.sleep(0.05)
        n = count_keys(log)
        print(f"      目标实际收到按键: {n} 次")
        ok &= check("保存后启动能真正投递按键", n >= 2, f"({n})")

        print("\n[4] 运行中修改参数并保存")
        before_iv = eng.targets[0].interval_sec
        app.v_interval.set("2.0")
        root.update()
        app.save_task()
        root.update()
        after_iv = eng.targets[0].interval_sec
        print(f"      间隔 {before_iv} -> {after_iv}")
        ok &= check("运行中改参数立即生效", abs(after_iv - 2.0) < 1e-6,
                    f"({after_iv})")

        print("\n[5] 停止")
        app.toggle_run()
        root.update()
        t_stop = time.time()
        while time.time() - t_stop < 1.5:
            root.update()
            time.sleep(0.05)
        n_after_stop = count_keys(log)
        time.sleep(1.0)
        n_later = count_keys(log)
        print(f"      停止时 {n_after_stop} 次 -> 1秒后 {n_later} 次")
        ok &= check("停止后不再投递", n_later == n_after_stop,
                    f"({n_after_stop} -> {n_later})")

        print("\n[6] 配置持久化：重启后能读到")
        eng.save()
        eng2 = Engine(CFG)
        print(f"      重启后任务: {[t.name for t in eng2.targets]}")
        ok &= check("重启后任务名正确",
                    any(t.name == "山海主号" for t in eng2.targets))
        t2 = next((t for t in eng2.targets if t.name == "山海主号"), None)
        ok &= check("重启后参数正确",
                    t2 is not None and t2.title_sub == "SH_RUNFLOW"
                    and abs(t2.interval_sec - 2.0) < 1e-6)

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
        if proc:
            proc.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
