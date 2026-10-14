"""开机画面测试替身：合成的小 splash（4×8 BMP）、横图、内存分区。"""
import io
import struct

from PIL import Image

from openpilot.system.lanlinkd import splash

RED, BLUE = (255, 0, 0), (0, 0, 255)
BMP_W, BMP_H = 4, 8  # 竖屏缓冲区；屏幕上看到的是 8×4 横图
HEADER = b"DDPH" + struct.pack("<I", 1) + bytes(56)
TAIL = b"\xAA" * 32


def make_splash(fill=(0, 0, 0)) -> bytes:
  pixels = bytes(reversed(fill)) * (BMP_W * BMP_H)  # BGR
  bmp = b"BM" + struct.pack("<IHHI", 54 + len(pixels), 0, 0, 54)
  bmp += struct.pack("<IiiHHIIiiII", 40, BMP_W, BMP_H, 1, 24, 0, len(pixels), 0, 0, 0, 0)
  return HEADER + bmp + pixels + TAIL


def landscape_png(top=RED, bottom=BLUE) -> bytes:
  img = Image.new("RGB", (BMP_H, BMP_W), bottom)
  img.paste(top, (0, 0, BMP_H, BMP_W // 2))
  out = io.BytesIO()
  img.save(out, "PNG")
  return out.getvalue()


def bmp_rows(head: bytes) -> list[list[tuple[int, int, int]]]:
  """按 BMP 存储顺序（自下而上）返回每行的 RGB 像素。"""
  start, end = splash.pixel_span(head)
  data = head[start:end]
  row = BMP_W * 3
  return [[tuple(reversed(data[r * row + c * 3:r * row + c * 3 + 3])) for c in range(BMP_W)] for r in range(BMP_H)]


class FakePartition:
  def __init__(self, data: bytes):
    self.data = bytearray(data)
    self.writes = 0

  def read(self, n: int) -> bytes:
    return bytes(self.data[:n])

  def write(self, data: bytes) -> None:
    self.writes += 1
    self.data[:len(data)] = data
