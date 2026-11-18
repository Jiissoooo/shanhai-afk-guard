"""test_task_crud.py - 任务增删改与运行流程回归测试。

针对用户实际操作路径：
    新建 -> 选程序 -> 填参数 -> 保存 -> 启动 -> 删除

重点覆盖开发中发现的两个真实缺陷：
  1) del_task 先把 self.sel 置 -1 再过滤实例，导致过滤条件形同虚设，
     被删任务的实例残留在引擎里继续按键。
  2) 删除中间某个任务后，后续任务的 target_idx 没有同步左移，
     导致实例被错误地归到别的任务名下（按错任务的按键/间隔执行）。
"""
from __future__ import annotations

import json
import os
import sys
import time
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app.engine import Engine, Target  # noqa: E402
from app.ui import App                 # noqa: E402
from app import winapi as W            # noqa: E402

CFG = os.path.join(ROOT, "config", "test_crud.json")


def check(label, cond, extra=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label} {extra}")
    return cond


def main() -> int:
    print("=" * 72)
    print(" 任务增删改 + 运行流程 回归测试")
    print("=" * 72)
    ok = True
    if os.path.exists(CFG):
        os.remove(CFG)

    root = None
    try:
        eng = Engine(CFG)
        eng.targets = [
            Target(name="任务A", exe_sub="A.exe"),
            Target(name="任务B", exe_sub="B.exe"),
            Target(name="任务C", exe_sub="C.exe"),
        ]
        root = tk.Tk()
        app = App(root, eng)
        root.update()

        print("\n[1] 初始三条任务")
        rows = app.tree.get_children()
        print(f"      表格行数 = {len(rows)}")
        for i, r in enumerate(rows):
            print(f"        {i}: {app.tree.item(r, 'values')[0]}")
        ok &= check("表格显示 3 条", len(rows) == 3)

        # 模拟引擎接管了三个任务各自的实例
        from app.engine import Instance
        now = time.monotonic()
        eng.instances = [
            Instance(target_idx=0, target_name="任务A", hwnd=0x1001,
                     pid=111, title="A窗口", exe="A.exe", next_fire=now + 5),
            Instance(target_idx=1, target_name="任务B", hwnd=0x1002,
                     pid=222, title="B窗口", exe="B.exe", next_fire=now + 5),
            Instance(target_idx=2, target_name="任务C", hwnd=0x1003,
                     pid=333, title="C窗口", exe="C.exe", next_fire=now + 5),
        ]
        print(f"      注入实例: {[(i.target_idx, i.target_name) for i in eng.instances]}")

        print("\n[2] 删除中间那条（任务B，索引1）")
        rows = app.tree.get_children()
        app.tree.selection_set(rows[1])     # 选中任务B
        root.update()
        ok &= check("选中项为任务B", app.v_name.get() == "任务B",
                    f"(实际 {app.v_name.get()!r})")

        # 绕过确认框直接执行删除逻辑（下面会单独测确认框）
        import app.ui as UI
        orig_ask = UI.messagebox.askyesno
        UI.messagebox.askyesno = lambda *a, **k: True
        try:
            app.del_task()
        finally:
            UI.messagebox.askyesno = orig_ask
        root.update()

        names = [t.name for t in eng.targets]
        print(f"      删除后剩余任务: {names}")
        ok &= check("任务B 已删除", "任务B" not in names, f"({names})")
        ok &= check("剩余 2 条", len(eng.targets) == 2, f"({len(eng.targets)})")

        print("\n[3] 被删任务的实例必须被清理（原 bug：实例残留）")
        inst_names = [i.target_name for i in eng.instances]
        print(f"      剩余实例: {inst_names}")
        ok &= check("任务B 的实例已移除",
                    all("任务B" != n for n in inst_names),
                    f"({inst_names})")

        print("\n[4] 剩余实例的 target_idx 必须与新列表对齐（原 bug：错位）")
        bad = []
        for i in eng.instances:
            if not (0 <= i.target_idx < len(eng.targets)):
                bad.append((i.target_name, i.target_idx, "越界"))
                continue
            expect = eng.targets[i.target_idx].name
            if expect != i.target_name:
                bad.append((i.target_name, i.target_idx,
                            f"应指向{expect}"))
        print(f"      不一致项: {bad if bad else '无'}")
        ok &= check("所有实例索引正确对齐", not bad, f"({bad})")

        print("\n[5] 删除后表格已刷新")
        rows2 = app.tree.get_children()
        vals = [app.tree.item(r, "values")[0] for r in rows2]
        print(f"      表格内容: {vals}")
        ok &= check("表格显示 2 条", len(rows2) == 2, f"({len(rows2)})")
        ok &= check("表格不含任务B", "任务B" not in vals)

        print("\n[6] 新建任务")
        before = len(eng.targets)
        app.new_task()
        root.update()
        print(f"      任务数 {before} -> {len(eng.targets)}")
        ok &= check("新建成功", len(eng.targets) == before + 1)
        ok &= check("表格同步", len(app.tree.get_children()) == before + 1)

        print("\n[7] 保存后落盘")
        rows3 = app.tree.get_children()
        app.tree.selection_set(rows3[-1])
        root.update()
        app.v_name.set("落盘测试")
        app.v_exe.set("TestApp.exe")
        app.v_key.set("f5")
        app.v_interval.set("45")
        app.save_task()
        root.update()
        with open(CFG, encoding="utf-8") as fh:
            data = json.load(fh)
        saved = [t["name"] for t in data["targets"]]
        print(f"      磁盘上的任务: {saved}")
        ok &= check("落盘含新任务", "落盘测试" in saved)
        t_saved = next(t for t in data["targets"] if t["name"] == "落盘测试")
        ok &= check("参数正确保存",
                    t_saved["key"] == "f5" and t_saved["interval_sec"] == 45,
                    f"(key={t_saved['key']}, itv={t_saved['interval_sec']})")

        print("\n[8] 未选任务时点删除不崩溃")
        app.sel = -1
        try:
            app.del_task()
            ok &= check("未选中时安全返回", True)
        except Exception as exc:
            ok &= check("未选中时安全返回", False, repr(exc))

        print("\n[9] 取消删除确认时不动数据")
        rows4 = app.tree.get_children()
        app.tree.selection_set(rows4[0])
        root.update()
        n_before = len(eng.targets)
        UI.messagebox.askyesno = lambda *a, **k: False   # 用户点"否"
        try:
            app.del_task()
        finally:
            UI.messagebox.askyesno = orig_ask
        ok &= check("点否后任务数不变", len(eng.targets) == n_before,
                    f"({n_before} -> {len(eng.targets)})")

        print("\n[10] 表格选中与表单同步")
        rows5 = app.tree.get_children()
        if len(rows5) >= 2:
            app.tree.selection_set(rows5[1])
            root.update()
            print(f"      选中第2行 -> 表单任务名 = {app.v_name.get()!r}")
            ok &= check("表单已同步选中项",
                        app.v_name.get() == eng.targets[1].name,
                        f"({app.v_name.get()!r})")

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


if __name__ == "__main__":
    raise SystemExit(main())
