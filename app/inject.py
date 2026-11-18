"""inject.py - 三种按键注入实现，后台/前台都能用。

method = "message"  : PostMessage(WM_KEYDOWN/UP)。目标不需要前台，可以最小化。
                      直接投递到目标 GUI 线程的焦点子窗口（模拟器场景必用）。
                      缺点：走 DirectInput / RawInput 的游戏会忽略它。
method = "sendinput" : 硬件级注入。仅当目标已是前台时生效，兼容性最好。
method = "focus"     : 闪切前台 -> SendInput -> 闪回原前台。兼容 DirectInput /
                      RawInput 游戏，代价是每次会短暂抢焦点（约 120ms）。
method = "both"      : message 为主；若目标恰好在前台再补一次 sendinput（默认）。
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes as wt

from . import winapi as W

user32 = W.user32

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_EXTENDEDKEY = 0x0001

SW_RESTORE = 9
SW_MINIMIZE = 6


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wt.UINT
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.PostMessageW.restype = wt.BOOL
user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
user32.AttachThreadInput.restype = wt.BOOL
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.SetForegroundWindow.restype = wt.BOOL
user32.BringWindowToTop.argtypes = [wt.HWND]
user32.BringWindowToTop.restype = wt.BOOL
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.ShowWindow.restype = wt.BOOL
user32.GetForegroundWindow.restype = wt.HWND


def _lparam(vk: int, up: bool) -> int:
    scan = W.scan_from_vk(vk)
    lp = 1                      # repeat count
    lp |= (scan & 0xFF) << 16   # scan code
    if W.is_extended_vk(vk):
        lp |= 1 << 24           # extended
    if W.is_syskey_vk(vk):
        lp |= 1 << 29           # context code: alt 已按住
    if up:
        lp |= (1 << 30) | (1 << 31)  # previous state=down, transition=release
    return lp


def post_key(hwnd: int, vk: int, hold_ms: int = 40) -> bool:
    """向 hwnd 投递一次按下+抬起。返回是否至少成功投递了按下消息。"""
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    target = W.focus_hwnd_of_target(hwnd)
    down_msg = WM_SYSKEYDOWN if W.is_syskey_vk(vk) else WM_KEYDOWN
    up_msg = WM_SYSKEYUP if W.is_syskey_vk(vk) else WM_KEYUP
    ok = bool(user32.PostMessageW(target, down_msg, vk, _lparam(vk, False)))
    if hold_ms > 0:
        time.sleep(hold_ms / 1000.0)
    user32.PostMessageW(target, up_msg, vk, _lparam(vk, True))
    return ok


def send_input_key(vk: int, hold_ms: int = 40) -> bool:
    """硬件级注入，作用于当前前台窗口。"""
    scan = W.scan_from_vk(vk)
    flags = KEYEVENTF_SCANCODE
    if W.is_extended_vk(vk):
        flags |= KEYEVENTF_EXTENDEDKEY
    pair = (INPUT * 2)()
    for i, up in ((0, False), (1, True)):
        pair[i].type = INPUT_KEYBOARD
        pair[i].ki = KEYBDINPUT(wVk=vk, wScan=scan,
                                dwFlags=flags | (KEYEVENTF_KEYUP if up else 0),
                                time=0, dwExtraInfo=0)
    if not user32.SendInput(2, pair, ctypes.sizeof(INPUT)):
        return False
    if hold_ms > 0:
        time.sleep(hold_ms / 1000.0)
    return True


def _alt_unlock() -> None:
    """按下并释放一次 ALT，令本进程取得 SetForegroundWindow 的前台权限。

    Windows 的前台锁规则：进程刚产生过输入事件时才有权切换前台窗口。
    单独一个 ALT 在绝大多数游戏/模拟器里是无副作用的。
    """
    scan = W.scan_from_vk(0x12)
    pair = (INPUT * 2)()
    for i, up in ((0, False), (1, True)):
        pair[i].type = INPUT_KEYBOARD
        pair[i].ki = KEYBDINPUT(wVk=0x12, wScan=scan,
                                dwFlags=(KEYEVENTF_KEYUP if up else 0),
                                time=0, dwExtraInfo=0)
    user32.SendInput(2, pair, ctypes.sizeof(INPUT))


def force_foreground(hwnd: int, tries: int = 3) -> bool:
    """把 hwnd 抢到前台，带重试与状态变更兜底。

    实测发现的关键行为（矩阵测试 0/6 vs 6/6）：
      已可见且未最小化的窗口，直接 AttachThreadInput + SetForegroundWindow
      会稳定失败——它不在前台历史里，前台锁拒绝切换；
      而最小化的窗口因为 SW_RESTORE 触发了一次状态变更，反而 6/6 成功。

    所以兜底不是"多按一次 ALT"，而是**制造一次真实的状态变更**：
      退化为 SW_MINIMIZE -> SW_RESTORE，强制窗口重新进入前台候选。
    """
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)

    def _attach_steal() -> bool:
        fg = user32.GetForegroundWindow()
        tid_fg = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        tid_self = W.kernel32.GetCurrentThreadId()
        attached = False
        if tid_fg and tid_fg != tid_self:
            attached = bool(user32.AttachThreadInput(tid_self, tid_fg, True))
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(tid_self, tid_fg, False)
        return user32.GetForegroundWindow() == hwnd

    if _attach_steal():
        return True

    for attempt in range(tries):
        if user32.GetForegroundWindow() == hwnd:
            return True
        # 制造状态变更：最小化再还原，让窗口重新成为前台候选
        if not user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_MINIMIZE)
            time.sleep(0.05)
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.05)
        if _attach_steal():
            return True
        # 仍失败则用 ALT 取得前台权限后重试
        _alt_unlock()
        time.sleep(0.04)
        user32.SetForegroundWindow(hwnd)
        if user32.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.08 * (attempt + 1))
    return user32.GetForegroundWindow() == hwnd


def flash_foreground_key(hwnd: int, vk: int, hold_ms: int = 40,
                         settle_ms: int = 60) -> bool:
    """闪切前台 -> SendInput -> 闪回原前台。

    用于 DirectInput / RawInput 类游戏：它们只认真实键盘输入，
    PostMessage 会被整条丢进队列无人处理。
    settle_ms 用于让目标窗口完成 WM_ACTIVATE 后再被按键，否则偶发丢键。
    """
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    prev = user32.GetForegroundWindow()
    if not force_foreground(hwnd):
        return False
    time.sleep(settle_ms / 1000.0)
    ok = send_input_key(vk, hold_ms)
    time.sleep(0.03)
    if prev and prev != hwnd and user32.IsWindow(prev):
        force_foreground(prev)
    return ok


def press(hwnd: int, vk: int, method: str = "both", hold_ms: int = 40) -> dict:
    """统一入口，返回 {'ok':bool,'via':str}。"""
    if not hwnd or not user32.IsWindow(hwnd):
        return {"ok": False, "via": "dead-window"}
    via = "none"
    ok = False
    if method in ("message", "both"):
        ok = post_key(hwnd, vk, hold_ms)
        via = "message"
    if method == "focus":
        ok = flash_foreground_key(hwnd, vk, hold_ms)
        return {"ok": ok, "via": "focus"}
    if method in ("sendinput", "both"):
        # 只有目标此刻真的在前台，sendinput 才打得准
        fg = user32.GetForegroundWindow()
        if fg and (fg == hwnd or user32.IsChild(hwnd, fg)
                   or user32.GetParent(fg) == hwnd):
            ok = send_input_key(vk, hold_ms) or ok
            via = "sendinput" if ok else via
        elif method == "sendinput":
            # 单用 sendinput 且目标不在前台 -> 主动闪切，别静默丢键
            ok = flash_foreground_key(hwnd, vk, hold_ms)
            via = "sendinput(flash)"
    return {"ok": ok, "via": via}
