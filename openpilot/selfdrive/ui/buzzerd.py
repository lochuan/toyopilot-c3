#!/usr/bin/env python3
"""
C3XL 板载有源蜂鸣器（GPIO.SIREN = 42）具有固定音色，用声音长短和间隔区分场景。
libbuzzer_player 在 SCHED_FIFO 下按绝对时刻翻转 GPIO。
可用 python -m openpilot.selfdrive.ui.buzzerd engage disengage refuse prompt warning 试听。
"""
import ctypes
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from openpilot.cereal import log, messaging
from openpilot.common.gpio import gpio_export
from openpilot.common.hardware.comma.pins import GPIO
from openpilot.common.realtime import Ratekeeper
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.ui.soundd import check_selfdrive_timeout_alert
from openpilot.sunnypilot.selfdrive.ui.quiet_mode import QuietMode

AudibleAlert = log.SelfdriveState.AudibleAlert


class BuzzerSegment(NamedTuple):
  on_seconds: float
  chop_hz: float | None  # 斩波影响音色，频率不保证对应音高；None = 不斩波，最亮最响
  gap_seconds: float  # 这一段之后的静音


BuzzerSound = tuple[BuzzerSegment, ...]

ENGAGE_SOUND: BuzzerSound = (BuzzerSegment(0.04, None, 0.05), BuzzerSegment(0.085, None, 0.))  # 短接长
DISENGAGE_SOUND: BuzzerSound = (BuzzerSegment(0.10, None, 0.075), BuzzerSegment(0.04, None, 0.))  # 长接短
REFUSE_SOUND: BuzzerSound = (BuzzerSegment(0.045, None, 0.10), BuzzerSegment(0.045, None, 0.))  # 等长双点
PROMPT_SOUND: BuzzerSound = (BuzzerSegment(0.045, None, 0.),)
WARNING_SOUND: BuzzerSound = (BuzzerSegment(0.05, None, 0.04), BuzzerSegment(0.05, None, 0.04), BuzzerSegment(0.12, None, 0.))

PREVIEW_SOUNDS = {
  "engage": ENGAGE_SOUND,
  "disengage": DISENGAGE_SOUND,
  "refuse": REFUSE_SOUND,
  "prompt": PROMPT_SOUND,
  "warning": WARNING_SOUND,
}

SCENE_SOUNDS = {
  AudibleAlert.engage: ENGAGE_SOUND,
  AudibleAlert.disengage: DISENGAGE_SOUND,
  AudibleAlert.refuse: REFUSE_SOUND,
  AudibleAlert.warningSoft: WARNING_SOUND,
  AudibleAlert.warningImmediate: WARNING_SOUND,
}  # 其余提示（prompt/promptRepeat/promptDistracted/preAlert）都放 PROMPT_SOUND


def sound_edges(sound: BuzzerSound) -> list[float]:
  edges = []
  t = 0.
  for segment in sound:
    if segment.chop_hz is None:
      edges.extend((round(t, 6), round(t + segment.on_seconds, 6)))
      t += segment.on_seconds
    else:
      half_period = 0.5 / segment.chop_hz
      for _ in range(round(segment.on_seconds * segment.chop_hz)):
        edges.extend((round(t, 6), round(t + half_period, 6)))
        t += 2 * half_period
    t += segment.gap_seconds
  return edges


def open_buzzer_gpio() -> int | None:
  gpio_export(GPIO.SIREN)
  # export 后 udev（99-gpio.rules）异步把权限交给 gpio 组，实测约 3 s；写失败就等它就绪再试，否则这次 onroad 全程不响
  for _ in range(200):
    try:
      with open(f"/sys/class/gpio/gpio{GPIO.SIREN}/direction", "w") as f:
        f.write("out")
      value_fd = os.open(f"/sys/class/gpio/gpio{GPIO.SIREN}/value", os.O_WRONLY)
    except OSError:
      time.sleep(0.05)
      continue
    # 保持 fd 打开直接写：斩波每毫秒要开关两次，每次重新 open 太慢
    return value_fd
  cloudlog.error("buzzerd: siren gpio still not writable after 10 s, exiting so manager restarts and retries")
  return None


def load_buzzer_player(value_fd: int) -> Callable[[BuzzerSound], None]:
  player = ctypes.CDLL(str(Path(__file__).with_name("libbuzzer_player.so")))
  player.buzzer_play_edges.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_double), ctypes.c_size_t]
  player.buzzer_play_edges.restype = ctypes.c_int

  def play(sound: BuzzerSound) -> None:
    try:
      edges = sound_edges(sound)
      edge_array = (ctypes.c_double * len(edges))(*edges)
      ret = player.buzzer_play_edges(value_fd, edge_array, len(edges))
      if ret != 0:
        cloudlog.error(f"buzzerd: buzzer_play_edges failed: {os.strerror(-ret)}")
    finally:
      # SIGINT 在 C 调用返回后才处理；C 播放结束时也会关闭蜂鸣器。
      os.write(value_fd, b"0")

  return play


class Buzzerd(QuietMode):
  def __init__(self, play_scene_sound: Callable[[BuzzerSound], None]):
    super().__init__()
    self.play_scene_sound = play_scene_sound
    self.current_alert = AudibleAlert.none
    self.selfdrive_timeout_alert = False

  def update_alert(self, new_alert: int) -> None:
    if new_alert == self.current_alert:
      return
    self.current_alert = new_alert
    if self.should_play_sound(new_alert):
      self.play_scene_sound(SCENE_SOUNDS.get(new_alert, PROMPT_SOUND))

  def update_from_messages(self, sm) -> None:
    if sm.updated['selfdriveState']:
      self.update_alert(sm['selfdriveState'].alertSound.raw)
    elif check_selfdrive_timeout_alert(sm):
      self.update_alert(AudibleAlert.warningImmediate)
      self.selfdrive_timeout_alert = True
    elif self.selfdrive_timeout_alert:
      # 同 soundd：掉线警告结束后复位，selfdrived 恢复后的下一个提示才会被当成切换
      self.update_alert(AudibleAlert.none)
      self.selfdrive_timeout_alert = False

  def buzzerd_thread(self) -> None:
    sm = messaging.SubMaster(['selfdriveState', 'selfdriveStateSP'])
    rk = Ratekeeper(20, print_delay_threshold=None)  # 放声音会占住循环最长约 0.45 s，滞后是预期的
    while True:
      sm.update(0)
      self.load_param()
      self.update_from_messages(sm)
      rk.keep_time()


def main():
  fd = open_buzzer_gpio()
  if fd is None:
    return
  play = load_buzzer_player(fd)
  if len(sys.argv) > 1:
    for name in sys.argv[1:]:
      play(PREVIEW_SOUNDS[name])
      time.sleep(0.6)
    return
  Buzzerd(play).buzzerd_thread()


if __name__ == "__main__":
  main()
