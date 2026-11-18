"""winapi.py - Win32 共享层。

职责：窗口枚举 / 进程名解析 / 前台焦点查询 / 虚拟键与扫描码映射。
所有 ctypes 原型集中在这里，其它模块只管业务。
"""
from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes as wt

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MAX_PATH = 260


# ---------------------------------------------------------------- structures
class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("flags", wt.DWORD),
        ("hwndActive", wt.HWND),
        ("hwndFocus", wt.HWND),
        ("hwndCapture", wt.HWND),
        ("hwndMenuOwner", wt.HWND),
        ("hwndMoveSize", wt.HWND),
        ("hwndCaret", wt.HWND),
        ("rcCaret", RECT),
    ]


WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


# ---------------------------------------------------------------- prototypes
user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
user32.EnumWindows.restype = wt.BOOL
user32.EnumChildWindows.argtypes = [wt.HWND, WNDENUMPROC, wt.LPARAM]
user32.EnumChildWindows.restype = wt.BOOL

user32.IsWindow.argtypes = [wt.HWND]
user32.IsWindow.restype = wt.BOOL
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsWindowVisible.restype = wt.BOOL
user32.IsIconic.argtypes = [wt.HWND]
user32.IsIconic.restype = wt.BOOL
user32.IsChild.argtypes = [wt.HWND, wt.HWND]
user32.IsChild.restype = wt.BOOL
user32.GetParent.argtypes = [wt.HWND]
user32.GetParent.restype = wt.HWND

user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int

user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.GetForegroundWindow.restype = wt.HWND
user32.GetFocus.restype = wt.HWND

user32.GetGUIThreadInfo.argtypes = [wt.DWORD, ctypes.POINTER(GUITHREADINFO)]
user32.GetGUIThreadInfo.restype = wt.BOOL

user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(RECT)]
user32.GetClientRect.restype = wt.BOOL

user32.MapVirtualKeyW.argtypes = [wt.UINT, wt.UINT]
user32.MapVirtualKeyW.restype = wt.UINT

user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short

kernel32.GetCurrentThreadId.restype = wt.DWORD
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.CloseHandle.restype = wt.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wt.BOOL


# ---------------------------------------------------------------- helpers
def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def get_window_text(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def get_class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


_EXE_CACHE: dict[int, str] = {}


def get_exe_name(pid: int) -> str:
    """进程可执行文件名（含 .exe）。权限不足返回空串。"""
    if pid in _EXE_CACHE:
        return _EXE_CACHE[pid]
    name = ""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if h:
        try:
            size = wt.DWORD(MAX_PATH * 4)
            buf = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                name = os.path.basename(buf.value)
        finally:
            kernel32.CloseHandle(h)
    _EXE_CACHE[pid] = name
    return name


def window_info(hwnd: int) -> dict:
    pid = wt.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    rc = RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rc))
    wr = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(wr))
    return {
        "hwnd": int(hwnd),
        "title": get_window_text(hwnd),
        "cls": get_class_name(hwnd),
        "pid": int(pid.value),
        "exe": get_exe_name(int(pid.value)),
        "w": rc.right - rc.left,
        "h": rc.bottom - rc.top,
        "rw": wr.right - wr.left,
        "rh": wr.bottom - wr.top,
        "visible": bool(user32.IsWindowVisible(hwnd)),
        "minimized": bool(user32.IsIconic(hwnd)),
    }


def list_windows(include_hidden: bool = False) -> list[dict]:
    """枚举顶层窗口。"""
    out: list[dict] = []
    live = []
    buf = []

    @WNDENUMPROC
    def _cb(hwnd, lparam):
        if not include_hidden and not user32.IsWindowVisible(hwnd):
            return True
        info = window_info(hwnd)
        buf.append(info)
        return True

    live.append(_cb)  # 保持回调引用，避免 GC
    user32.EnumWindows(_cb, 0)
    out = buf
    return out


def _match_one(rule: str, hay: str) -> bool:
    """大小写不敏感子串匹配。hay 必须先归一化，否则标题大小写会导致漏匹配。"""
    r = (rule or "").strip().lower()
    h = (hay or "").lower()
    if not r:
        return False
    if r in h:
        return True
    # 允许不带 .exe 后缀，例如规则 "game" 命中 "game.exe"
    if h.endswith(".exe") and r == h[:-4]:
        return True
    return False


def get_window_rect(hwnd: int) -> tuple[int, int]:
    """窗口矩形尺寸。最小化时 GetClientRect 返回 0x0，但窗口矩形仍有有效值。"""
    r = RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return r.right - r.left, r.bottom - r.top
    return 0, 0


def is_real_app_window(info: dict) -> bool:
    """判断是否值得接管的「真正的应用主窗口」。

    枚举 include_hidden 时会捞出大量辅助窗口，例如 wegame 的
    WECHAT_AUTH_MESSAGE_WIN / TCLS_CORE_WND / tpg_cross_msgs_wnd /
    GDI+ Window / no_active_wnd / ClassName<数字> 等。这些窗口
    收到按键毫无意义，还会把界面刷满、把真窗口挤掉。

    过滤规则（任一不满足即丢弃）：
      1. 必须可见（最小化仍算可见 —— 这是后台运行的前提）
      2. 必须有非空标题
      3. 尺寸必须像主窗口；**最小化的窗口客户端尺寸是 0x0，必须豁免**，
         否则「最小化后继续工作」这个核心功能会被自己的过滤规则杀掉
      4. 排除已知的系统/框架辅助窗口类
    """
    if not info.get("visible"):
        return False
    title = (info.get("title") or "").strip()
    if not title:
        return False
    cls = (info.get("cls") or "").lower()
    junk_cls = {
        "gdi+ window", "no_active_wnd", "shell_traywnd", "progman",
        "workerw", "msctfime ui", "ime", "default ime",
        "tooltips_class32", "sysshadow",
    }
    if cls in junk_cls:
        return False
    # ClassName 后面直接跟数字的（如 ClassName497694437）基本都是内部辅助窗
    if cls.startswith("classname") and cls[9:].isdigit():
        return False
    low = title.lower()
    junk_title = ("gdip", "default ime", "msctfime", "cross_msg",
                  "cross_mgs", "auth_message", "_wnd_", "tcls_core",
                  "hidden window", "wxtrayicon", "trayicon", "notify_wnd")
    if any(j in low for j in junk_title):
        return False
    # 尺寸检查：最小化窗口豁免（用窗口矩形而非客户区作为兜底）
    if info.get("minimized"):
        return True
    w, h = info.get("w", 0), info.get("h", 0)
    if w < 100 or h < 100:
        rw, rh = info.get("rw", 0), info.get("rh", 0)
        if rw < 100 or rh < 100:
            return False
    return True


def find_windows(title_sub: str = "", exe_sub: str = "",
                 include_hidden: bool = False,
                 include_own: bool = False,
                 real_only: bool = True,
                 match_all: bool = False,
                 limit: int = 32) -> list[dict]:
    """按窗口标题 / 进程名子串匹配，返回全部命中窗口（天然支持多开同进程）。

    real_only=True（默认）时只返回真正的主窗口，避免接管 wegame 那类
    程序的一堆隐藏辅助窗口。测试里需要枚举全部窗口时传 False。

    match_all=False（默认，OR）：标题或进程名任一命中即算匹配。
    match_all=True （AND）：**两个条件都必须满足**。
        多开场景必须用 AND：同一进程（如 python.exe / 模拟器）下会跑多个
        互不相关的程序，只用 OR 会把它们全部接管。界面里选程序并自动
        填入标题关键字后，必须按 AND 收窄。
        若其中一个条件为空，则退化为只按另一个条件匹配。
    """
    t_rule = (title_sub or "").strip()
    e_rule = (exe_sub or "").strip()
    if not t_rule and not e_rule:
        return []
    own = os.getpid()
    hits = []
    for w in list_windows(include_hidden=include_hidden):
        if not include_own and w["pid"] == own:
            continue
        if real_only and not is_real_app_window(w):
            continue
        t_ok = _match_one(t_rule, w["title"]) if t_rule else False
        e_ok = _match_one(e_rule, w["exe"]) if e_rule else False
        if match_all:
            # 两个规则都给了就必须都满足；只给一个则按那一个
            if t_rule and e_rule:
                hit = t_ok and e_ok
            else:
                hit = t_ok or e_ok
        else:
            hit = t_ok or e_ok
        if hit:
            hits.append(w)
            if len(hits) >= limit:
                break
    return hits


def foreground_hwnd() -> int:
    return int(user32.GetForegroundWindow() or 0)


def list_apps(include_own: bool = False) -> list[dict]:
    """枚举「可选择的程序」清单，按 exe 聚合，供界面下拉框使用。

    每条记录：
        exe        进程名（如 Game.exe）
        windows    该进程的主窗口数（>1 说明是多开）
        titles     前几个窗口标题，用于下拉框里辅助辨认
        pids       进程 ID 列表
        hwnds      主窗口句柄列表
        minimized  是否全部窗口都最小化
        控件:      是否值得显示（有真实主窗口）
    按窗口数降序、进程名升序排列，游戏/多开程序自然排在前面。
    """
    own = os.getpid()
    raw = list_windows(include_hidden=True)
    buckets: dict[str, dict] = {}
    for w in raw:
        if not w["exe"]:
            continue
        if not include_own and w["pid"] == own:
            continue
        if not is_real_app_window(w):
            continue
        key = w["exe"]
        b = buckets.get(key)
        if b is None:
            b = buckets[key] = {
                "exe": key, "windows": 0, "titles": [], "all_titles": [],
                "pids": [], "hwnds": [], "all_minimized": True, "max_area": 0,
            }
        b["windows"] += 1
        b["hwnds"].append(w["hwnd"])
        if w["pid"] not in b["pids"]:
            b["pids"].append(w["pid"])
        # 收集所有标题（用于多开时提取公共前缀，不能只留 3 个）
        t = (w["title"] or "").strip()
        if t and t not in b["all_titles"]:
            b["all_titles"].append(t)
        if t and len(b["titles"]) < 3 and t not in b["titles"]:
            b["titles"].append(t)
        if not w["minimized"]:
            b["all_minimized"] = False
        b["max_area"] = max(b["max_area"], w["w"] * w["h"])
    out = list(buckets.values())
    out.sort(key=lambda x: (-x["windows"], x["exe"].lower()))
    return out


def display_name(app: dict) -> str:
    """给下拉框用的显示文本：程序名 + 多开数 + 窗口标题。"""
    exe = app["exe"]
    base = exe[:-4] if exe.lower().endswith(".exe") else exe
    n = app["windows"]
    tag = f"[{n}个窗口] " if n > 1 else ""
    title = app["titles"][0][:40] if app["titles"] else ""
    return f"{tag}{base}  ·  {title}" if title else f"{tag}{base}"


def focus_hwnd_of_target(hwnd: int) -> int:
    """取目标窗口所在 GUI 线程当前的键盘焦点窗口，取不到则返回 hwnd 本身。

    模拟器（雷电/MuMu/蓝叠）把输入收到子窗口里，直接对顶层窗口 PostMessage
    往往无效，需要投递到真正拥有焦点的子窗口。
    """
    tid = user32.GetWindowThreadProcessId(hwnd, None)
    if tid:
        gti = GUITHREADINFO()
        gti.cbSize = ctypes.sizeof(GUITHREADINFO)
        if user32.GetGUIThreadInfo(tid, ctypes.byref(gti)) and gti.hwndFocus:
            f = int(gti.hwndFocus)
            if f == hwnd or user32.IsChild(hwnd, f) or user32.GetParent(f) == hwnd:
                return f
    return hwnd


# ---------------------------------------------------------------- VK / scan
VK_NAMED: dict[str, int] = {
    "back": 0x08, "backspace": 0x08, "tk": 0x09, "tab": 0x09, "clear": 0x0C,
    "enter": 0x0D, "return": 0x0D, "shift": 0x10, "ctrl": 0x11, "control": 0x11,
    "alt": 0x12, "menu": 0x12, "pause": 0x13, "capslock": 0x14, "caps": 0x14,
    "esc": 0x1B, "escape": 0x1B, "space": 0x20, "pageup": 0x21, "pgup": 0x21,
    "pagedown": 0x22, "pgdn": 0x22, "end": 0x23, "home": 0x24,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "printscreen": 0x2C, "prtsc": 0x2C, "insert": 0x2D, "ins": 0x2D,
    "delete": 0x2E, "del": 0x2E,
    "lwin": 0x5B, "rwin": 0x5C, "apps": 0x5D,
    "numpad0": 0x60, "numpad1": 0x61, "numpad2": 0x62, "numpad3": 0x63,
    "numpad4": 0x64, "numpad5": 0x65, "numpad6": 0x66, "numpad7": 0x67,
    "numpad8": 0x68, "numpad9": 0x69,
    "multiply": 0x6A, "add": 0x6B, "separator": 0x6C, "subtract": 0x6D,
    "decimal": 0x6E, "divide": 0x6F,
    "numlock": 0x90, "scrolllock": 0x91,
    "lshift": 0xA0, "rshift": 0xA1, "lctrl": 0xA2, "rctrl": 0xA3,
    "lalt": 0xA4, "ralt": 0xA5,
    "semicolon": 0xBA, "equals": 0xBB, "comma": 0xBC, "minus": 0xBD,
    "period": 0xBE, "slash": 0xBF, "grave": 0xC0,
    "lbracket": 0xDB, "backslash": 0xDC, "rbracket": 0xDD, "quote": 0xDE,
}
for _i in range(1, 25):
    VK_NAMED[f"f{_i}"] = 0x6F + _i  # F1=0x70 ... F24=0x87

# 需要置扩展位(bit24)的键（MS 文档 Extended-Key 列表）
VK_EXTENDED = {
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,  # PgUp PgDn End Home 方向键
    0x2C,                                            # PrintScreen
    0x2D, 0x2E,                                      # Insert Delete
    0x6F,                                            # 小键盘 /
    0x90,                                            # NumLock
    0xA3, 0xA5,                                      # 右 Ctrl / 右 Alt
}
# 走 WM_SYSKEY* 的键（Alt 系）
VK_SYSKEYS = {0x12, 0xA4, 0xA5, 0x73}  # Alt / 左右 Alt / F10


def vk_from_name(name: str) -> int:
    """'space' / 'a' / 'F8' / '0x20' -> VK code。"""
    n = (name or "").strip().lower()
    if not n:
        raise ValueError("空按键名")
    if n.startswith("0x"):
        return int(n, 16)
    if n in VK_NAMED:
        return VK_NAMED[n]
    if len(n) == 1:
        ch = n.upper()
        if ch.isascii() and (ch.isalpha() or ch.isdigit()):
            return ord(ch)
    raise ValueError(f"无法识别的按键: {name!r}")


def scan_from_vk(vk: int) -> int:
    return int(user32.MapVirtualKeyW(vk, 0)) & 0xFF  # MAPVK_VK_TO_VSC


def is_extended_vk(vk: int) -> bool:
    return vk in VK_EXTENDED


def is_syskey_vk(vk: int) -> bool:
    return vk in VK_SYSKEYS


def vk_down(vk: int) -> bool:
    """物理按键当前是否按下（用于全局热键轮询）。"""
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)
