"""二维码生成（离线可用，不依赖任何在线服务）。

用 ``qrcode`` 库直接输出 **SVG**：

- 不依赖 Pillow，也不产生位图，打印时任意缩放都清晰（标签打印的关键）；
- 生成过程完全在本机完成，适合内网离线部署。

渲染方式：``qrcode`` 的 ``SvgPathImage`` 把二维码画成一条 path，
体积小、浏览器与主流打印驱动都支持。
"""
import io

import qrcode
import qrcode.image.svg


def qr_svg(data, box_size=10, border=2):
    """把文本编码为二维码，返回 SVG 字符串（UTF-8）。"""
    factory = qrcode.image.svg.SvgPathImage
    img = qrcode.make(
        str(data),
        image_factory=factory,
        box_size=box_size,
        border=border,
    )
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode('utf-8')
