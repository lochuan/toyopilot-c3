from openpilot.system.hardware.hardwared import offroad_idle_for_5_min

NOW = 10_000.


def test_boot_is_not_offroad_idle():
  # 开机那一阵负载高，CPU 单核会冲到 85°C 上下；这不是“熄火闲置还很热”，
  # 不能套 OFFROAD_DANGER_TEMP 预冷，否则每次开机都弹过热提示、晚上路
  assert not offroad_idle_for_5_min(started_ts=None, off_ts=None, now=NOW)
  assert not offroad_idle_for_5_min(started_ts=None, off_ts=NOW - 30, now=NOW)


def test_onroad_is_not_offroad_idle():
  assert not offroad_idle_for_5_min(started_ts=NOW - 600, off_ts=None, now=NOW)


def test_offroad_more_than_5_min_is_idle():
  assert offroad_idle_for_5_min(started_ts=None, off_ts=NOW - 301, now=NOW)
