"""make_icon.py - 生成托盘图标 assets/tray.ico。

配色与程序界面一致：深底 + 青色山形 + 蓝点。
多尺寸（16/32/48/64/256），托盘会用 16x16，任务栏用 32x32。
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "tray.ico")


def build(size: int = 256) -> Image.Image:
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 圆角深色底
    d.rounded_rectangle([2, 2, s - 2, s - 2], radius=int(s * 0.19),
                        fill=(24, 28, 38, 255))
    # 山形（青色，与界面成功色 #5fd38d 一致）
    d.polygon([
        (int(s * 0.12), int(s * 0.74)),
        (int(s * 0.375), int(s * 0.29)),
        (int(s * 0.547), int(s * 0.586)),
        (int(s * 0.695), int(s * 0.375)),
        (int(s * 0.883), int(s * 0.74)),
    ], fill=(95, 211, 141, 255))
    # 山顶亮点（蓝，与界面 info 色一致）
    r = s * 0.047
    cx, cy = s * 0.375, s * 0.255
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(138, 180, 248, 255))
    return img


def main() -> int:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img = build(256)
    img.save(OUT, format="ICO",
             sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"written {OUT} ({os.path.getsize(OUT)} bytes)")
    # 同时输出 png 便于展示
    png = os.path.join(os.path.dirname(OUT), "tray_preview.png")
    img.save(png, format="PNG")
    print(f"written {png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
