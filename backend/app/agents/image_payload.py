"""处理发给多模态模型的图纸图片，供功能 Agent 构造图片输入使用。"""

import base64
import struct
import zlib
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def build_model_image_data_url(file_path: Path, mime_type: str, max_side: int) -> str:
    """读取图片并在必要时压缩成模型更容易处理的 data URL。"""
    if mime_type == "image/png":
        compressed = resize_png_bytes(file_path.read_bytes(), max_side)
        if compressed:
            return f"data:image/png;base64,{base64.b64encode(compressed).decode('ascii')}"

    encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def resize_png_bytes(data: bytes, max_side: int) -> bytes:
    """把常见 8 位 PNG 缩小到指定长边，失败时返回空字节。"""
    try:
        width, height, color_type, raw = decode_png(data)
    except ValueError:
        return b""

    if max(width, height) <= max_side:
        return data

    scale = max_side / max(width, height)
    target_width = max(1, round(width * scale))
    target_height = max(1, round(height * scale))
    rgb = resize_rgb(raw, width, height, color_type, target_width, target_height)
    return encode_png(target_width, target_height, rgb)


def decode_png(data: bytes) -> tuple[int, int, int, bytes]:
    """解码当前项目常见的非交错 RGB/RGBA PNG。"""
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("不是 PNG 文件。")

    offset = len(PNG_SIGNATURE)
    width = height = color_type = bit_depth = interlace = None
    compressed_parts: list[bytes] = []
    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(
                ">IIBBBBB", chunk_data
            )
        elif chunk_type == b"IDAT":
            compressed_parts.append(chunk_data)
        elif chunk_type == b"IEND":
            break

    if (
        not width
        or not height
        or bit_depth != 8
        or color_type not in {2, 6}
        or interlace != 0
    ):
        raise ValueError("PNG 格式暂不支持自动缩小。")

    bpp = 4 if color_type == 6 else 3
    decompressed = zlib.decompress(b"".join(compressed_parts))
    return width, height, color_type, unfilter_png(decompressed, width, height, bpp)


def unfilter_png(data: bytes, width: int, height: int, bpp: int) -> bytes:
    """还原 PNG 每一行的过滤数据。"""
    row_bytes = width * bpp
    rows: list[bytearray] = []
    offset = 0
    previous = bytearray(row_bytes)
    for _ in range(height):
        filter_type = data[offset]
        offset += 1
        row = bytearray(data[offset : offset + row_bytes])
        offset += row_bytes
        for index in range(row_bytes):
            left = row[index - bpp] if index >= bpp else 0
            up = previous[index]
            upper_left = previous[index - bpp] if index >= bpp else 0
            if filter_type == 1:
                row[index] = (row[index] + left) & 0xFF
            elif filter_type == 2:
                row[index] = (row[index] + up) & 0xFF
            elif filter_type == 3:
                row[index] = (row[index] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                row[index] = (row[index] + paeth(left, up, upper_left)) & 0xFF
            elif filter_type != 0:
                raise ValueError("PNG 过滤类型不支持。")
        rows.append(row)
        previous = row
    return b"".join(rows)


def resize_rgb(
    raw: bytes,
    width: int,
    height: int,
    color_type: int,
    target_width: int,
    target_height: int,
) -> bytes:
    """用近邻采样缩小图纸，保持线条可见。"""
    source_bpp = 4 if color_type == 6 else 3
    output = bytearray(target_width * target_height * 3)
    for y in range(target_height):
        source_y = min(height - 1, int(y * height / target_height))
        for x in range(target_width):
            source_x = min(width - 1, int(x * width / target_width))
            source_index = (source_y * width + source_x) * source_bpp
            target_index = (y * target_width + x) * 3
            r, g, b = raw[source_index : source_index + 3]
            if color_type == 6:
                alpha = raw[source_index + 3]
                r = (r * alpha + 255 * (255 - alpha)) // 255
                g = (g * alpha + 255 * (255 - alpha)) // 255
                b = (b * alpha + 255 * (255 - alpha)) // 255
            output[target_index : target_index + 3] = bytes((r, g, b))
    return bytes(output)


def encode_png(width: int, height: int, rgb: bytes) -> bytes:
    """把 RGB 数据重新编码为 PNG。"""
    rows = []
    row_bytes = width * 3
    for y in range(height):
        start = y * row_bytes
        rows.append(b"\x00" + rgb[start : start + row_bytes])
    data = PNG_SIGNATURE
    data += png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    data += png_chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
    data += png_chunk(b"IEND", b"")
    return data


def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    """创建 PNG 数据块。"""
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def paeth(left: int, up: int, upper_left: int) -> int:
    """计算 PNG Paeth 预测值。"""
    estimate = left + up - upper_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= up_distance and left_distance <= upper_left_distance:
        return left
    if up_distance <= upper_left_distance:
        return up
    return upper_left
