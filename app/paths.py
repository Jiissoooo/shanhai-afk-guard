"""paths.py - 统一解析「程序目录」与「打包后资源目录」。

源码运行时两者相同；PyInstaller 单文件打包后必须区分：
  - resource_dir()  只读资源（assets/tray.ico），在解包出来的 _MEIPASS 里
  - app_dir()       可写数据（config/targets.json），必须是 **exe 所在目录**
                    —— 写进 _MEIPASS 的话，进程退出即消失，配置无法持久化

这是打包版最容易踩的坑：单文件 exe 每次启动都会把资源解压到一个新的
临时目录，把 config 放在那里面等于「存了等于没存」。
"""
from __future__ import annotations

import os
import sys


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> str:
    """只读资源根目录（assets/ 的父目录）。"""
    if is_frozen():
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return base
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def app_dir() -> str:
    """可写数据根目录（config/ 的父目录）。打包后是 exe 所在目录。"""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(*parts: str) -> str:
    return os.path.join(resource_dir(), *parts)


def app_path(*parts: str) -> str:
    return os.path.join(app_dir(), *parts)
