"""tray.py - 纯 Win32 系统托盘图标（不依赖第三方库）。

为什么自己写：
    pystray 需要联网安装，而本机 PyPI 不可达；
    而 Shell_NotifyIcon 是 Windows 自带能力，ctypes 直接调用即可。

实现要点：
    - 需要有一个隐藏的 message-only 窗口来接收托盘回调消息
    - 托盘消息循环跑在独立线程里，不能阻塞 Tk 主线程
    - 右键菜单用 CreatePopupMenu + TrackPopupMenu
    - 左键单击/双击恢复主窗口
"""
from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes as wt

from . import winapi as W

user32 = W.user32
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = W.kernel32

# ---------------------------------------------------------------- constants
WM_USER = 0x0400
WM_TRAYICON = WM_USER + 20
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
WM_QUIT = 0x0012

NIM_ADD = 0x0
NIM_MODIFY = 0x1
NIM_DELETE = 0x2
NIF_MESSAGE = 0x01
NIF_ICON = 0x02
NIF_TIP = 0x04
NIF_INFO = 0x10

NIIF_INFO = 0x01
NIIF_WARNING = 0x02

MF_STRING = 0x0000
MF_SEPARATOR = 0x0800
MF_GRAYED = 0x0001
MF_CHECKED = 0x0008
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100

SW_HIDE = 0
SW_SHOW = 5
SW_RESTORE = 9

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040
IDI_APPLICATION = 32512

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT,
                             wt.WPARAM, wt.LPARAM)

# 菜单项 ID
CMD_SHOW = 1001
CMD_TOGGLE = 1002
CMD_STOPALL = 1003
CMD_INFO = 1004
CMD_SEP = 1005
CMD_EXIT = 1006


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("hWnd", wt.HWND),
        ("uID", wt.UINT),
        ("uFlags", wt.UINT),
        ("uCallbackMessage", wt.UINT),
        ("hIcon", wt.HICON),
        ("szTip", wt.WCHAR * 128),
        ("dwState", wt.DWORD),
        ("dwStateMask", wt.DWORD),
        ("szInfo", wt.WCHAR * 256),
        ("uVersion", wt.UINT),
        ("szInfoTitle", wt.WCHAR * 64),
        ("dwInfoFlags", wt.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wt.HICON),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wt.UINT), ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wt.HWND), ("message", wt.UINT),
                ("wParam", wt.WPARAM), ("lParam", wt.LPARAM),
                ("time", wt.DWORD), ("pt", POINT)]


# ---------------------------------------------------------------- prototypes
shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wt.BOOL

user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wt.ATOM
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, wt.HWND, wt.HMENU,
                                   wt.HINSTANCE, wt.LPVOID]
user32.CreateWindowExW.restype = wt.HWND
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.DestroyWindow.argtypes = [wt.HWND]
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wt.HWND, wt.UINT, wt.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.CreatePopupMenu.restype = wt.HMENU
user32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, ctypes.c_size_t, wt.LPCWSTR]
user32.AppendMenuW.restype = wt.BOOL
user32.DestroyMenu.argtypes = [wt.HMENU]
user32.TrackPopupMenu.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, wt.HWND, ctypes.c_void_p]
user32.TrackPopupMenu.restype = ctypes.c_int
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.LoadIconW.argtypes = [wt.HINSTANCE, wt.LPVOID]
user32.LoadIconW.restype = wt.HICON
user32.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT,
                              ctypes.c_int, ctypes.c_int, wt.UINT]
user32.LoadImageW.restype = wt.HANDLE
user32.DestroyIcon.argtypes = [wt.HICON]


def _make_icon(path: str | None):
    """加载托盘图标；文件缺失时退回系统默认图标。"""
    if path and os.path.exists(path):
        try:
            h = user32.LoadImageW(None, path, IMAGE_ICON, 0, 0,
                                  LR_LOADFROMFILE | LR_DEFAULTSIZE)
            if h:
                return h, True
        except Exception:
            pass
    h = user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
    return h, False


class TrayIcon:
    """系统托盘图标。

    callbacks:
        on_show()      左键单击或菜单"打开主窗口"
        on_toggle()    菜单"启动/暂停"
        on_stopall()   菜单"全部停止"
        on_exit()      菜单"退出"
        get_state()    -> dict(running=bool, count=int) 用于菜单勾选与提示
    """

    def __init__(self, title: str, icon_path: str | None = None,
                 callbacks: dict | None = None):
        self.title = title
        self.icon_path = icon_path
        self.cb = callbacks or {}
        self._hwnd = None
        self._thread = None
        self._ready = threading.Event()
        self._visible = False
        self._icon = None
        self._owns_icon = False
        self._cls = f"ShanhaiTray_{os.getpid()}_{id(self)}"
        self._wndproc_ref = None

    # ------------------------------------------------------------ lifecycle
    def start(self, timeout: float = 3.0) -> bool:
        """启动托盘线程。返回图标是否在超时内真正注册成功。

        注意：不能只看事件标志——线程可能因异常提前退出并置位 finally。
        必须同时确认 _visible（Shell_NotifyIcon 已成功）。
        """
        if self._thread and self._thread.is_alive() and self._visible:
            return True
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="helmd-tray",
                                        daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        return bool(self._visible)

    def stop(self):
        """移除图标并结束线程。"""
        if self._hwnd:
            try:
                self._remove()
                user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
            except Exception:
                pass
        self._hwnd = None

    def is_visible(self) -> bool:
        return self._visible

    # ------------------------------------------------------------ internals
    def _run(self):
        try:
            hinst = kernel32.GetModuleHandleW(None)
            self._icon, self._owns_icon = _make_icon(self.icon_path)

            @WNDPROC
            def wndproc(hwnd, msg, wparam, lparam):
                if msg == WM_TRAYICON:
                    low = lparam & 0xFFFF
                    if low in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                        self._invoke("on_show")
                        return 0
                    if low in (WM_RBUTTONUP, WM_CONTEXTMENU):
                        self._popup_menu()
                        return 0
                    return 0
                if msg == WM_COMMAND:
                    return self._on_command(int(wparam) & 0xFFFF)
                if msg == WM_CLOSE:
                    user32.DestroyWindow(hwnd)
                    return 0
                if msg == WM_DESTROY:
                    user32.PostQuitMessage(0)
                    return 0
                return user32.DefWindowProcW(hwnd, msg, wparam,
                                             ctypes.c_ssize_t(lparam).value)

            self._wndproc_ref = wndproc  # 防止被 GC
            wc = WNDCLASSW()
            wc.lpfnWndProc = wndproc
            wc.hInstance = hinst
            wc.lpszClassName = self._cls
            user32.RegisterClassW(ctypes.byref(wc))

            # message-only 窗口（HWND_MESSAGE = -3）
            self._hwnd = user32.CreateWindowExW(
                0, self._cls, self.title, 0, 0, 0, 0, 0,
                wt.HWND(-3), None, hinst, None)
            if not self._hwnd:
                self._ready.set()
                return

            self._add()
            # 关键：图标注册成功后才算就绪，否则 start() 会误判失败。
            # 之前把它放在 finally 里，导致 _run 抛异常也会置位为"就绪"。
            self._ready.set()

            msg = MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception:
            pass
        finally:
            # 兜底：任何路径退出都要唤醒等待者，避免 start() 永久阻塞
            self._ready.set()

    def _base_data(self) -> NOTIFYICONDATAW:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        return nid

    def _add(self):
        if not self._hwnd:
            return
        nid = self._base_data()
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self._icon
        nid.szTip = self._tooltip_text()
        if shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
            self._visible = True

    def _remove(self):
        if not self._hwnd:
            return
        nid = self._base_data()
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        self._visible = False
        if self._owns_icon and self._icon:
            user32.DestroyIcon(self._icon)

    def _tooltip_text(self) -> str:
        st = {}
        try:
            if "get_state" in self.cb:
                st = self.cb["get_state"]() or {}
        except Exception:
            pass
        running = st.get("running")
        count = st.get("count", 0)
        state = "运行中" if running else "已暂停"
        txt = f"{self.title} · {state} · 接管{count}窗口"
        return txt[:127]

    def _refresh(self):
        """更新提示文字与菜单状态。"""
        if not self._hwnd:
            return
        nid = self._base_data()
        nid.uFlags = NIF_TIP
        nid.szTip = self._tooltip_text()
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def notify(self, title: str, text: str, warning: bool = False):
        """气泡提示（点击关闭到托盘时给用户一个可见反馈）。"""
        if not self._hwnd:
            return
        nid = self._base_data()
        nid.uFlags = NIF_INFO
        nid.szInfoTitle = title[:63]
        nid.szInfo = text[:255]
        nid.dwInfoFlags = NIIF_WARNING if warning else NIIF_INFO
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def _popup_menu(self):
        st = {}
        try:
            if "get_state" in self.cb:
                st = self.cb["get_state"]() or {}
        except Exception:
            pass
        running = bool(st.get("running"))
        count = st.get("count", 0)

        hmenu = user32.CreatePopupMenu()
        try:
            user32.AppendMenuW(hmenu, MF_STRING, CMD_SHOW, "打开主窗口")
            user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
            label = "暂停 (F9)" if running else "启动 (F9)"
            user32.AppendMenuW(hmenu, MF_STRING, CMD_TOGGLE, label)
            user32.AppendMenuW(
                hmenu, MF_STRING | (0 if running else MF_GRAYED),
                CMD_STOPALL, "全部停止 (F10)")
            user32.AppendMenuW(
                hmenu, MF_STRING | MF_GRAYED, CMD_INFO,
                f"当前接管 {count} 个窗口")
            user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(hmenu, MF_STRING, CMD_EXIT, "退出程序")

            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            # 必须先置前台，否则菜单不消失（Windows 已知行为）
            user32.SetForegroundWindow(self._hwnd)
            cmd = user32.TrackPopupMenu(
                hmenu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
                pt.x, pt.y, 0, self._hwnd, None)
            if cmd:
                self._on_command(cmd)
        finally:
            user32.DestroyMenu(hmenu)

    def _on_command(self, cmd: int) -> int:
        if cmd == CMD_SHOW:
            self._invoke("on_show")
        elif cmd == CMD_TOGGLE:
            self._invoke("on_toggle")
            self._refresh()
        elif cmd == CMD_STOPALL:
            self._invoke("on_stopall")
            self._refresh()
        elif cmd == CMD_EXIT:
            self._invoke("on_exit")
        return 0

    def _invoke(self, name: str):
        fn = self.cb.get(name)
        if not fn:
            return
        try:
            fn()
        except Exception:
            pass
