"""test_exe_launcher.py - 原生 exe 启动器端到端测试。

验证用户报的三个问题都被解决：
  1) 不再出现黑色命令框  -> 启动后不存在 conhost 子进程 / exe 是 GUI 子系统
  2) 关掉终端不会杀程序  -> 启动器退出后 GUI 仍在运行
  3) 直接是 exe 文件      -> 双击 exe 就能启动
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes as wt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app import winapi as W      # noqa: E402
from app import integrity as I   # noqa: E402

EXE = os.path.join(ROOT, "build", "山海寻灵防AFK.exe")
WM_CLOSE = 0x0010


def check(label, cond, extra=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label} {extra}")
    return cond


def find_gui():
    for w in W.list_windows(include_hidden=True):
        if w["exe"].lower().startswith("pythonw") and \
                (w["title"] or "").startswith("山海寻灵"):
            return w
    return None


def kill_pythonw():
    subprocess.run(["taskkill", "/F", "/IM", "pythonw.exe"],
                   capture_output=True)


def main() -> int:
    print("=" * 70)
    print(" 原生 exe 启动器端到端测试")
    print("=" * 70)
    ok = True

    if not os.path.exists(EXE):
        print(f"  exe 不存在: {EXE}")
        return 1
    print(f"\n  目标: {os.path.basename(EXE)}  "
          f"{os.path.getsize(EXE)} bytes")

    # --- 1) PE 子系统
    print("\n[1] PE 子系统（是否 GUI，决定会不会有黑框）")
    with open(EXE, "rb") as fh:
        data = fh.read()
    pe = int.from_bytes(data[0x3C:0x40], "little")
    subsystem = int.from_bytes(data[pe + 24 + 68:pe + 24 + 70], "little")
    ok &= check(f"Subsystem={subsystem} 应为 2(GUI)", subsystem == 2)

    # --- 2) manifest 提权声明
    print("\n[2] 提权声明")
    txt = data.decode("utf-8", "ignore")
    ok &= check("requireAdministrator 已嵌入", "requireAdministrator" in txt)

    # --- 3) 启动并观察
    print("\n[3] 启动 exe（会弹 UAC，若已提权则由外层代理执行）")
    kill_pythonw()
    time.sleep(0.5)

    # 记录启动前已存在的 conhost 数量，用于对比
    def conhost_count():
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq conhost.exe",
                            "/NH"], capture_output=True, text=True)
        return r.stdout.lower().count("conhost.exe")
    before_conhost = conhost_count()
    print(f"    启动前 conhost 数量: {before_conhost}")

    proc = subprocess.Popen([EXE], cwd=ROOT,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    time.sleep(6)

    gui = find_gui()
    ok &= check("GUI 已启动（pythonw + 山海寻灵标题）",
                gui is not None,
                f"(pid={gui['pid']})" if gui else "(未找到)")

    if gui:
        rid = I.process_integrity(gui["pid"])
        print(f"    GUI 完整性级别: {I.il_name(rid)}")
        ok &= check("GUI 是管理员(High)完整性", rid >= I.IL_HIGH,
                    f"({I.il_name(rid)})")
        ok &= check("GUI 解释器是 pythonw.exe（无控制台）",
                    gui["exe"].lower().startswith("pythonw"),
                    f"({gui['exe']})")

        # --- 4) 启动器自身已退出
        print("\n[4] 启动器是否已退出（不留常驻）")
        time.sleep(1)
        ok &= check("启动器进程已退出", proc.poll() is not None,
                    f"(exit={proc.poll()})")

        # --- 5) 关掉启动器后 GUI 仍活着（用户核心诉求）
        print("\n[5] 关掉启动器后 GUI 是否仍运行（用户核心诉求）")
        alive = find_gui() is not None
        ok &= check("启动器退出后 GUI 仍在运行", alive)

        # --- 6) conhost 增量
        print("\n[6] 是否产生新的 conhost 控制台宿主")
        after_conhost = conhost_count()
        print(f"    启动后 conhost 数量: {after_conhost}")
        ok &= check("没有新增 conhost（无黑框）",
                    after_conhost <= before_conhost + 0,
                    f"({before_conhost} -> {after_conhost})")

        # 收尾：关闭 GUI
        W.user32.PostMessageW(gui["hwnd"], WM_CLOSE, 0, 0)
        time.sleep(1.5)
        still = find_gui()
        print(f"    关闭后残留: {'有' if still else '无'}")
        if still:
            kill_pythonw()

    print("\n" + "=" * 70)
    print(f" 结果: {'全部通过' if ok else '存在失败项'}")
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
