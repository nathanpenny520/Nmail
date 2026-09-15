#!/usr/bin/env python3
"""从母版图生成 Nmail 全套图标资产（仅需开发机跑一次，产物入库供 CI 打包）。

输入: personal-data/Nmail邮箱应用图标.png（2048×2048，黑底不透明，蓝色圆角方块居中）
处理: 裁剪到圆角方块包围盒 → 黑底按最大通道软阈值转透明（保留抗锯齿边缘）
输出:
    frontend/public/favicon.ico         16/32/48（浏览器标签页）
    frontend/public/icon-192.png        高分屏标签页/固定标签
    frontend/public/icon-512.png        同上 + 未来 PWA
    frontend/public/apple-touch-icon.png  180 满幅重排（渐变底+信封，Apple 自行裁圆角）
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


def apple_touch(master: Image.Image, size: int = 180, zoom: float = 1.06) -> Image.Image:
    """按 Apple 规范生成 apple-touch-icon（图内不自带圆角与外阴影，HIG）。

    母版放大 zoom 倍居中裁切：烘焙在图里的边缘光晕/暗边随之移出画布，系统蒙版
    裁出的圆角外沿只剩纯渐变蓝。放大后四角会露出母版圆角外的透明月牙——用圆弧
    内侧对角取样色铺双线性渐变补底，与周围渐变同色，肉眼不可见。
    """
    w, h = master.size
    px = master.convert("RGB").load()
    corners = [(int(w * fx), int(h * fy)) for fx, fy in ((0.06, 0.06), (0.94, 0.06), (0.06, 0.94), (0.94, 0.94))]
    bg = Image.new("RGB", (2, 2))
    bg.putdata([px[x, y] for x, y in corners])  # TL, TR, BL, BR
    bg = bg.resize((w, h), Image.BILINEAR)
    art = master.resize((round(w * zoom), round(h * zoom)), Image.LANCZOS)
    bg.paste(art, (round(w * (1 - zoom) / 2), round(h * (1 - zoom) / 2)), art)
    return bg.resize((size, size), Image.LANCZOS)


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

    # 随包分发（pip wheel package-data + nmail.spec datas）：桌面图标生成用
    appassets = ROOT / "backend" / "app" / "assets"
    appassets.mkdir(parents=True, exist_ok=True)
    m256.save(appassets / "nmail.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    master.save(appassets / "nmail.icns", format="ICNS",
                append_images=[master.resize((s, s), Image.LANCZOS) for s in (512, 256, 128, 64, 32, 16)])
    (appassets / "nmail-512.png").write_bytes((pub / "icon-512.png").read_bytes())

    # apple-touch-icon：满幅重排，圆角交给系统蒙版（见 apple_touch 文档串）
    apple_touch(master).save(pub / "apple-touch-icon.png")

    print("theme-color: #{:02x}{:02x}{:02x}".format(*master.getpixel((512, 4))[:3]))
    for p in sorted((*assets.glob("nmail.*"), assets / "icon-master.png", *pub.iterdir())):
        print(f"  {p.relative_to(ROOT)}  {p.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
