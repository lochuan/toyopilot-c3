# system/lanlinkd/splash.py
"""开机画面（splash 分区，lanlink 的 /api/splash）。

分区格式（C3/C3XL 的 Qualcomm logo，参考 Desktop/splash_maker）：b"DDPH" 头，后接一张
24 位 BMP（1080×2160 竖屏，自下而上逐行、BGR），其后是固定填充。只换 BMP 像素、
只回写到像素末尾（约 7 MB），头和填充原样不动。

屏幕横置：设备实测 BMP 逆时针转 90° 才是屏幕所见。所以用户图按屏幕所见的横图
（2160×1080，其他尺寸等比缩放、留黑边）顺时针转 90° 写入。

第一次写入前把分区原内容存到 BACKUP_PATH，恢复时写回并删掉备份；
有没有备份就是“是否已自定义”。
"""
import base64
import io
import os
import struct
import subprocess
import threading

from PIL import Image, ImageOps

PARTITION = "/dev/disk/by-partlabel/splash"
BACKUP_PATH = "/data/lanlink/splash_original.bin"
PARTITION_READ_BYTES = 8 * 1024 * 1024  # 头 0x4000 + BMP 约 6.7 MB，8 MB 够覆盖
MAX_IMAGE_PIXELS = 40_000_000  # 解码前拦住超大图：设备内存有限，几百 MB 的解码会拖垮 lanlinkd
PREVIEW_SIZE = (720, 360)


class SplashFormatError(ValueError):
  pass


class InvalidImageError(ValueError):
  pass


class NoBackupError(Exception):
  pass


class WriteVerifyError(Exception):
  pass


class PartitionIOError(Exception):
  pass


def _layout(head: bytes) -> tuple[int, int, int, int]:
  """返回 (像素起点, 像素终点, BMP 宽, BMP 高)。"""
  if head[:4] != b"DDPH":
    raise SplashFormatError("splash 分区不是 DDPH 格式")
  bmp = head.find(b"BM", 8)
  if bmp < 0 or len(head) < bmp + 54:
    raise SplashFormatError("splash 分区里没有 BMP")
  (offset,) = struct.unpack_from("<I", head, bmp + 10)
  width, height = struct.unpack_from("<ii", head, bmp + 18)
  (bpp,) = struct.unpack_from("<H", head, bmp + 28)
  (compression,) = struct.unpack_from("<I", head, bmp + 30)
  # 只认无压缩、自下而上、行不需要补齐的 24 位 BMP（1080×2160 正好满足）
  if bpp != 24 or compression != 0 or width <= 0 or height <= 0 or (width * 3) % 4:
    raise SplashFormatError(f"不支持的 BMP：{width}×{height} {bpp}bpp 压缩={compression}")
  start = bmp + offset
  end = start + width * height * 3
  if len(head) < end:
    raise SplashFormatError("splash 分区数据不完整")
  return start, end, width, height


def pixel_span(head: bytes) -> tuple[int, int]:
  start, end, _, _ = _layout(head)
  return start, end


def compose(head: bytes, image_bytes: bytes) -> bytes:
  """把用户图片换进 head 的像素区，返回从分区开头到像素末尾的新内容。"""
  start, _, width, height = _layout(head)
  try:
    img = Image.open(io.BytesIO(image_bytes))
    if img.width * img.height > MAX_IMAGE_PIXELS:
      raise InvalidImageError(f"图片太大（{img.width}×{img.height}）")
    img = ImageOps.exif_transpose(img).convert("RGB")
  except InvalidImageError:
    raise
  except Exception as e:  # 用户上传的任意字节：各解码插件抛的异常五花八门
    raise InvalidImageError("无法识别的图片") from e
  # 前端已画成 2160×1080，这里是兜底：其他调用方传任意尺寸也按留黑边处理
  img = ImageOps.pad(img, (height, width), color="black")
  img = img.transpose(Image.Transpose.ROTATE_270).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
  return head[:start] + img.tobytes("raw", "BGR")


def preview_jpeg(head: bytes) -> bytes:
  """屏幕所见方向的缩略图。"""
  start, end, width, height = _layout(head)
  img = Image.frombytes("RGB", (width, height), head[start:end], "raw", "BGR", 0, -1)
  img = img.transpose(Image.Transpose.ROTATE_90)
  img.thumbnail(PREVIEW_SIZE)
  out = io.BytesIO()
  img.save(out, "JPEG", quality=85)
  return out.getvalue()


def _write_durably(path: str, data: bytes) -> None:
  """备份必须先落盘再改分区：否则此时断电，分区已改、备份却是空的，原画面就找不回来了。"""
  os.makedirs(os.path.dirname(path), exist_ok=True)
  tmp = path + ".tmp"
  with open(tmp, "wb") as f:
    f.write(data)
    f.flush()
    os.fsync(f.fileno())
  os.replace(tmp, path)
  dir_fd = os.open(os.path.dirname(path), os.O_RDONLY)
  try:
    os.fsync(dir_fd)
  finally:
    os.close(dir_fd)


class SplashPartition:
  """设备上的 splash 分区，root 才能读写（lanlinkd 以 comma 身份运行，走 sudo）。"""

  def __init__(self, path: str = PARTITION):
    self.path = path

  def read(self, n: int) -> bytes:
    return self._sudo(["head", "-c", str(n), self.path]).stdout

  def write(self, data: bytes) -> None:
    self._sudo(["dd", f"of={self.path}", "bs=1M", "conv=fsync", "status=none"], data)

  @staticmethod
  def _sudo(cmd: list[str], data: bytes | None = None) -> subprocess.CompletedProcess:
    try:
      return subprocess.run(["sudo", *cmd], input=data, capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError) as e:
      raise PartitionIOError(f"读写 splash 分区失败：{e}") from e


class SplashService:
  """读写都是阻塞 IO（约 7 MB），lanlinkd 用 asyncio.to_thread 调用；锁防并发写分区。"""

  def __init__(self, partition, backup_path: str = BACKUP_PATH):
    self.partition = partition
    self.backup_path = backup_path
    self._lock = threading.Lock()

  def status(self) -> dict:
    with self._lock:
      return self._status(self.partition.read(PARTITION_READ_BYTES))

  def replace(self, image_bytes: bytes) -> dict:
    with self._lock:
      head = self.partition.read(PARTITION_READ_BYTES)
      new = compose(head, image_bytes)
      if not os.path.exists(self.backup_path):
        os.makedirs(os.path.dirname(self.backup_path), exist_ok=True)
        _write_durably(self.backup_path, head[:len(new)])
      self._write_verified(new)
      return self._status(new)

  def restore(self) -> dict:
    with self._lock:
      if not os.path.exists(self.backup_path):
        raise NoBackupError("没有修改前的备份，开机画面未被 LANLink 改过")
      with open(self.backup_path, "rb") as f:
        original = f.read()
      pixel_span(original)  # 备份坏了就别往分区写
      self._write_verified(original)
      os.remove(self.backup_path)
      return self._status(original)

  def _write_verified(self, data: bytes) -> None:
    self.partition.write(data)
    if self.partition.read(len(data)) != data:
      raise WriteVerifyError("写入 splash 分区后回读不一致")

  def _status(self, head: bytes) -> dict:
    return {
      "customized": os.path.exists(self.backup_path),
      "preview": "data:image/jpeg;base64," + base64.b64encode(preview_jpeg(head)).decode(),
    }
