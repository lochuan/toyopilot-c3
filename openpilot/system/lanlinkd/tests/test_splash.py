"""开机画面：BMP 打包方向、只改像素区、原厂备份与恢复。"""
import io

import pytest
from PIL import Image

from openpilot.system.lanlinkd import splash
from openpilot.system.lanlinkd.tests.splash_fakes import BLUE, BMP_H, RED, FakePartition, bmp_rows, landscape_png, make_splash


class TestCompose:
  def test_screen_top_goes_to_bmp_right(self):
    # 设备实测：BMP 逆时针转 90° 才是屏幕所见，所以屏幕上方对应 BMP 的右边
    rows = bmp_rows(splash.compose(make_splash(), landscape_png()))
    assert all(r == [BLUE, BLUE, RED, RED] for r in rows)

  def test_only_pixels_change(self):
    original = make_splash()
    new = splash.compose(original, landscape_png())
    start, end = splash.pixel_span(original)
    assert len(new) == end
    assert new[:start] == original[:start]

  def test_any_size_is_letterboxed_onto_black(self):
    img = io.BytesIO()
    Image.new("RGB", (4, 4), RED).save(img, "PNG")  # 方图放进 8×4 横屏：左右留黑
    rows = bmp_rows(splash.compose(make_splash(fill=BLUE), img.getvalue()))
    assert rows[0][0] == (0, 0, 0) and rows[-1][0] == (0, 0, 0)  # 屏幕左右两端
    assert rows[BMP_H // 2][0] == RED

  def test_preview_shows_what_screen_shows(self):
    preview = Image.open(io.BytesIO(splash.preview_jpeg(splash.compose(make_splash(), landscape_png()))))
    top, bottom = preview.getpixel((preview.width // 2, 0)), preview.getpixel((preview.width // 2, preview.height - 1))
    assert top[0] > top[2] and bottom[2] > bottom[0]  # JPEG 有损，只比红蓝谁多

  def test_rejects_non_splash(self):
    with pytest.raises(splash.SplashFormatError):
      splash.pixel_span(b"\x00" * 128)

  def test_rejects_oversized_image_before_decoding(self, monkeypatch):
    monkeypatch.setattr(splash, "MAX_IMAGE_PIXELS", BMP_H * 4 - 1)
    with pytest.raises(splash.InvalidImageError, match="太大"):
      splash.compose(make_splash(), landscape_png())

  def test_rejects_garbage_image(self):
    with pytest.raises(splash.InvalidImageError):
      splash.compose(make_splash(), b"not an image")


class TestService:
  def test_first_replace_backs_up_original_once(self, tmp_path):
    original = make_splash()
    part = FakePartition(original)
    svc = splash.SplashService(part, str(tmp_path / "orig.bin"))
    assert not svc.status()["customized"]
    svc.replace(landscape_png())
    svc.replace(landscape_png(top=BLUE, bottom=RED))
    assert svc.status()["customized"]
    assert (tmp_path / "orig.bin").read_bytes() == original[:splash.pixel_span(original)[1]]

  def test_restore_writes_original_back_and_clears_backup(self, tmp_path):
    original = make_splash()
    part = FakePartition(original)
    svc = splash.SplashService(part, str(tmp_path / "orig.bin"))
    svc.replace(landscape_png())
    assert bytes(part.data) != original
    assert not svc.restore()["customized"]
    assert bytes(part.data) == original
    assert not (tmp_path / "orig.bin").exists()

  def test_restore_without_backup_is_refused(self, tmp_path):
    svc = splash.SplashService(FakePartition(make_splash()), str(tmp_path / "orig.bin"))
    with pytest.raises(splash.NoBackupError):
      svc.restore()

  def test_write_is_verified_by_reading_back(self, tmp_path):
    class LossyPartition(FakePartition):
      def write(self, data):
        pass
    svc = splash.SplashService(LossyPartition(make_splash()), str(tmp_path / "orig.bin"))
    with pytest.raises(splash.WriteVerifyError):
      svc.replace(landscape_png())
