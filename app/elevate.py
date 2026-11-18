"""elevate.py - 管理员提权与权限状态。

为什么要这个模块：
  Windows UIPI 规定，Medium 完整性进程不能向 High 完整性进程发窗口消息。
  游戏平台（WeGame/TASLogin/游戏本体）通常以管理员启动 -> High。
  所以本工具若以普通权限运行，对这些目标 PostMessage 会返回
  FALSE + ERROR_ACCESS_DENIED(5)，表现为「界面显示在线但游戏没反应」。

策略：
  - exe 打包时嵌 manifest 直接请求 asInvoker 之外的 highestAvailable
  - 脚本运行时用 ShellExecuteW("runas") 自重启
  - 已在管理员权限下则什么都不做，避免提权循环
"""
from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes as wt

from . import winapi as W

shell32 = ctypes.WinDLL("shell32", use_last_error=True)
shell32.ShellExecuteW.argtypes = [wt.HWND, wt.LPCWSTR, wt.LPWSTR,
                                  wt.LPCWSTR, wt.LPCWSTR, ctypes.c_int]
shell32.ShellExecuteW.restype = ctypes.c_void_p

SW_SHOWNORMAL = 1
ERROR_CANCELLED = 1223

# 传给子进程的标记，防止反复提权
ENV_ELEVATED = "HELMD_ELEVATED"


def is_elevated() -> bool:
    return W.is_admin()


def is_frozen() -> bool:
    """是否是 PyInstaller 打包后的 exe。"""
    return bool(getattr(sys, "frozen", False))


def relaunch_as_admin(wait: bool = False) -> int:
    """以管理员身份重启自身。返回 ShellExecuteW 的返回值。

    >32 表示成功。若用户点了 UAC 的「否」，返回 ERROR_CANCELLED(1223)。
    """
    if is_frozen():
        exe = sys.executable
        params = " ".join(f'"{a}"' for a in sys.argv[1:])
    else:
        exe = sys.executable
        script = os.path.abspath(sys.argv[0])
        rest = " ".join(f'"{a}"' for a in sys.argv[1:])
        params = f'"{script}"' + (f" {rest}" if rest else "")

    env = dict(os.environ)
    env[ENV_ELEVATED] = "1"

    # 用 cmd /c start 承载环境变量，ShellExecuteW 本身不接受 env
    verb = "runas"
    workdir = os.getcwd()
    try:
        rc = shell32.ShellExecuteW(None, verb, exe, params, workdir,
                                   SW_SHOWNORMAL)
        code = int(rc or 0)
    except Exception:
        code = 0
    if code > 32 and wait:
        sys.exit(0)
    return code


def ensure_elevated(auto: bool = False, quiet: bool = False) -> bool:
    """确保当前是管理员。返回 True 表示已是管理员（或提权成功接手）。

    auto=True   : 未提权则直接尝试提权并退出当前进程
    auto=False  : 只检测，返回 False 表示不是管理员
    """
    if is_elevated():
        return True
    if not auto:
        return False
    if os.environ.get(ENV_ELEVATED) == "1":
        # 已经尝试过提权还是非管理员，说明被 UAC 拒绝，不再重试
        if not quiet:
            print("[!] 提权被拒绝，继续以普通权限运行（高完整性目标将无法控制）")
        return False
    code = relaunch_as_admin()
    if code > 32:
        sys.exit(0)          # 让提权后的实例接管，当前退出
    if not quiet:
        print(f"[!] 提权失败/被取消 (code={code})，继续以普通权限运行")
    return False


def status_line() -> str:
    """给界面用的权限状态文本。"""
    if is_elevated():
        return "管理员 · 可控制全部目标"
    return "普通权限 · 高完整性目标(游戏平台)会被拦截"
