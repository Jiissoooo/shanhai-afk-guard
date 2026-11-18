"""run_all.py - 一键跑全部测试。"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable

SUITE = [
    ("自检", [PY, os.path.join(ROOT, "main.py"), "--check"]),
    ("配置回归", [PY, os.path.join(HERE, "test_config.py")]),
    ("窗口过滤", [PY, os.path.join(HERE, "test_window_filter.py")]),
    ("程序下拉框", [PY, os.path.join(HERE, "test_app_picker.py")]),
    ("任务增删改", [PY, os.path.join(HERE, "test_task_crud.py")]),
    ("填完怎么运行", [PY, os.path.join(HERE, "test_run_flow.py")]),
    ("多开精确匹配", [PY, os.path.join(HERE, "test_multiopen_pick.py")]),
    ("多窗口后台并发", [PY, os.path.join(HERE, "test_multitarget.py")]),
    ("同进程多开+抖动", [PY, os.path.join(HERE, "test_multiopen.py")]),
    ("抢前台", [PY, os.path.join(HERE, "test_foreground.py")]),
    ("双通道注入", [PY, os.path.join(HERE, "test_sendinput.py")]),
    ("系统托盘", [PY, os.path.join(HERE, "test_tray.py")]),
    ("关闭到托盘", [PY, os.path.join(HERE, "test_tray_e2e.py")]),
    ("UIPI拦截", [PY, os.path.join(HERE, "test_uipi.py")]),
    ("界面端到端", [PY, os.path.join(HERE, "test_gui_e2e.py")]),
]


def kill_probes():
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process python -ErrorAction SilentlyContinue | "
             "Where-Object {$_.MainWindowTitle -like 'SH_*' -or "
             "$_.MainWindowTitle -like 'AFK*'} | Stop-Process -Force"],
            capture_output=True, timeout=20)
        del out
    except Exception:
        pass


def main() -> int:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    results = []
    for name, cmd in SUITE:
        kill_probes()
        print("\n" + "#" * 70)
        print(f"# {name}")
        print("#" * 70)
        r = subprocess.run(cmd, cwd=ROOT, env=env)
        results.append((name, r.returncode))
    kill_probes()

    print("\n" + "=" * 70)
    print(" 汇总")
    print("=" * 70)
    for name, rc in results:
        print(f"  {'✔ PASS' if rc == 0 else '✘ FAIL'}  {name}  (exit={rc})")
    bad = [n for n, rc in results if rc != 0]
    print("=" * 70)
    print(f" {len(results) - len(bad)}/{len(results)} 通过"
          + (f"；失败: {', '.join(bad)}" if bad else ""))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
