#!/usr/bin/env python3
"""从母版图生成 Nmail 全套图标资产（仅需开发机跑一次，产物入库供 CI 打包）。

输入: personal-data/Nmail邮箱应用图标.png（2048×2048，黑底不透明，蓝色圆角方块居中）
处理: 裁剪到圆角方块包围盒 → 黑底按最大通道软阈值转透明（保留抗锯齿边缘）
输出:
    frontend/public/favicon.ico         16/32/48（浏览器标签页）
    frontend/public/icon-192.png        高分屏标签页/固定标签
    frontend/public/icon-512.png        同上 + 未来 PWA
    frontend/public/apple-touch-icon.png  180 满幅不透明（Apple 自行裁圆角）
    assets/icon-master.png              1024 带透明角母版
    assets/nmail.ico                    16–256 多尺寸（Windows exe，nmail.spec 引用）
    assets/nmail.icns                   macOS 打包

用法: .venv/Scripts/python scripts/gen_icons.py   （需 pip install pillow）
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "personal-data" / "Nmail邮箱应用图标.png"

# 黑底→透明的软阈值区间（按 max(R,G,B)）：低于 LO 全透明，高于 HI 全不透明，
# 中间线性过渡以保留圆角与边缘的抗锯齿。信封内部深藏蓝折线 max 通道远高于 HI，不受影响。
LO, HI = 12, 56


def cutout(img: Image.Image) -> Image.Image:
    """裁剪到图形包围盒并把黑底转透明。"""
    rgba = img.convert("RGBA")
    r, g, b, _ = rgba.split()
    bright = ImageChops.lighter(ImageChops.lighter(r, g), b)
    alpha = bright.point(
        lambda v: 0 if v <= LO else 255 if v >= HI else round((v - LO) * 255 / (HI - LO))
    )
    bbox = alpha.point(lambda v: 255 if v > 8 else 0).getbbox()
    rgba.putalpha(alpha)
    return rgba.crop(bbox)


def main() -> None:
    master = cutout(Image.open(SRC)).resize((1024, 1024), Image.LANCZOS)
    assets = ROOT / "assets"
    pub = ROOT / "frontend" / "public"
    assets.mkdir(exist_ok=True)
    pub.mkdir(exist_ok=True)

    master.save(assets / "icon-master.png")

    m256 = master.resize((256, 256), Image.LANCZOS)
    m256.save(
        assets / "nmail.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    m256.save(pub / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])

    # icns 需显式提供各尺寸（Pillow 会合并写入一个文件）
    master.save(
        assets / "nmail.icns",
        format="ICNS",
        append_images=[master.resize((s, s), Image.LANCZOS) for s in (512, 256, 128, 64, 32, 16)],
    )

    master.resize((192, 192), Image.LANCZOS).save(pub / "icon-192.png")
    master.resize((512, 512), Image.LANCZOS).save(pub / "icon-512.png")

    # apple-touch-icon 满幅不透明：圆角透出的四角以图标主色（方块顶边中点取样）填充
    edge = master.getpixel((512, 4))[:3]
    bg = Image.new("RGB", master.size, edge)
    bg.paste(master, mask=master.split()[3])
    bg.resize((180, 180), Image.LANCZOS).save(pub / "apple-touch-icon.png")

    print("theme-color: #{:02x}{:02x}{:02x}".format(*edge))
    for p in sorted((*assets.glob("nmail.*"), assets / "icon-master.png", *pub.iterdir())):
        print(f"  {p.relative_to(ROOT)}  {p.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
