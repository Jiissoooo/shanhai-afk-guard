"""integrity.py - 进程完整性级别 (Integrity Level) 检测与 UIPI 预检。

Windows 的 UIPI 规则：低完整性进程不能向高完整性进程发窗口消息 / SendInput，
PostMessage 会直接返回 FALSE 且 GetLastError()==5 (ERROR_ACCESS_DENIED)。

所以「要不要管理员启动」等价于：目标进程的 IL 是否高于本工具的 IL。
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes as wt

from . import winapi as W

advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

TOKEN_QUERY = 0x0008
TokenIntegrityLevel = 25
ERROR_ACCESS_DENIED = 5

IL_UNTRUSTED = 0x0000
IL_LOW = 0x1000
IL_MEDIUM = 0x2000
IL_HIGH = 0x3000
IL_SYSTEM = 0x4000
IL_PROTECTED = 0x8000

IL_NAMES = {
    IL_UNTRUSTED: "Untrusted",
    IL_LOW: "Low",
    IL_MEDIUM: "Medium",
    IL_HIGH: "High",
    IL_SYSTEM: "System",
    IL_PROTECTED: "Protected",
}


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wt.DWORD)]


class TOKEN_MANDATORY_LABEL(ctypes.Structure):
    _fields_ = [("Label", SID_AND_ATTRIBUTES)]


advapi32.OpenProcessToken.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.HANDLE)]
advapi32.OpenProcessToken.restype = wt.BOOL
advapi32.GetTokenInformation.argtypes = [
    wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]
advapi32.GetTokenInformation.restype = wt.BOOL
advapi32.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
advapi32.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wt.DWORD]
advapi32.GetSidSubAuthority.restype = ctypes.POINTER(wt.DWORD)


def process_integrity(pid: int) -> int:
    """返回目标进程的完整性 RID。打不开 token 返回 -1（通常意味着对方 IL 更高）。"""
    h = W.kernel32.OpenProcess(W.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return -1
    try:
        tok = wt.HANDLE()
        if not advapi32.OpenProcessToken(h, TOKEN_QUERY, ctypes.byref(tok)):
            return -1
        try:
            size = wt.DWORD(0)
            advapi32.GetTokenInformation(tok, TokenIntegrityLevel, None, 0,
                                         ctypes.byref(size))
            if not size.value:
                return -1
            buf = ctypes.create_string_buffer(size.value)
            if not advapi32.GetTokenInformation(tok, TokenIntegrityLevel, buf,
                                                size, ctypes.byref(size)):
                return -1
            label = ctypes.cast(buf, ctypes.POINTER(TOKEN_MANDATORY_LABEL)).contents
            sid = label.Label.Sid
            cnt = advapi32.GetSidSubAuthorityCount(sid).contents.value
            return int(advapi32.GetSidSubAuthority(sid, cnt - 1).contents.value)
        finally:
            W.kernel32.CloseHandle(tok)
    finally:
        W.kernel32.CloseHandle(h)


def il_name(rid: int) -> str:
    if rid < 0:
        return "Unknown(拒绝访问)"
    return IL_NAMES.get(rid, f"0x{rid:X}")


def self_integrity() -> int:
    return process_integrity(os.getpid())


def can_target(self_rid: int, target_rid: int) -> tuple[bool, str]:
    """判断能否向目标投递消息。返回 (是否可行, 说明)。"""
    if target_rid < 0:
        return False, "无法读取目标进程 token（通常说明目标权限更高，或已退出）"
    if target_rid > self_rid:
        return False, (f"目标 IL={il_name(target_rid)} 高于本工具 "
                       f"IL={il_name(self_rid)}，UIPI 会拦截 -> 需以管理员启动")
    return True, f"目标 IL={il_name(target_rid)} 不高于本工具 IL={il_name(self_rid)}，可以投递"


def preflight(windows: list[dict]) -> list[dict]:
    """对一批窗口做权限预检，返回每项 {hwnd,title,exe,pid,il,ok,reason}。"""
    me = self_integrity()
    out = []
    for w in windows:
        rid = process_integrity(w["pid"])
        ok, reason = can_target(me, rid)
        out.append({"hwnd": w["hwnd"], "title": w.get("title", ""),
                    "exe": w.get("exe", ""), "pid": w["pid"],
                    "il": rid, "il_name": il_name(rid),
                    "ok": ok, "reason": reason})
    return out


def blocked_targets(windows: list[dict]) -> list[dict]:
    return [r for r in preflight(windows) if not r["ok"]]
