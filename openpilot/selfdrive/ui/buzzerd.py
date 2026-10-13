#!/usr/bin/env python3
"""
C3XL 板载蜂鸣器（GPIO.SIREN = 42）：C3XL 的提示音由这个蜂鸣器发出，soundd 的扬声器上听不到。
selfdriveState.alertSound 每次切换时按场景放一段声音。蜂鸣器是有源的，音高固定，
靠在一声里快速开关（斩波）改出不同质感：80 Hz 低沉、1 kHz 柔和、不斩波最亮最响。
各场景的声音 2026-10-13 由用户在设备上逐个试听选定。
"""
import os
import time
from collections.abc import Callable
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
  chop_hz: float | None  # None = 不斩波，最亮最响
  gap_seconds: float  # 这一段之后的静音


BuzzerSound = tuple[BuzzerSegment, ...]

DEEP_CHOP_HZ = 80
SOFT_CHOP_HZ = 1000

ENGAGE_SOUND: BuzzerSound = (BuzzerSegment(0.15, DEEP_CHOP_HZ, 0.08), BuzzerSegment(0.15, DEEP_CHOP_HZ, 0.))  # 低沉「嘟嘟」
DISENGAGE_SOUND: BuzzerSound = (BuzzerSegment(0.4, DEEP_CHOP_HZ, 0.),)  # 低沉「嘟——」
REFUSE_SOUND: BuzzerSound = (BuzzerSegment(0.06, None, 0.05), BuzzerSegment(0.06, None, 0.))  # 急促「滴滴」
PROMPT_SOUND: BuzzerSound = (BuzzerSegment(0.2, SOFT_CHOP_HZ, 0.),)  # 柔和「哔」
WARNING_SOUND: BuzzerSound = (BuzzerSegment(0.07, None, 0.05),) * 3 + (BuzzerSegment(0.07, None, 0.),)  # 最响「滴滴滴滴」

SCENE_SOUNDS = {
  AudibleAlert.engage: ENGAGE_SOUND,
  AudibleAlert.disengage: DISENGAGE_SOUND,
  AudibleAlert.refuse: REFUSE_SOUND,
  AudibleAlert.warningSoft: WARNING_SOUND,
  AudibleAlert.warningImmediate: WARNING_SOUND,
}  # 其余提示（prompt/promptRepeat/promptDistracted/preAlert）都放 PROMPT_SOUND


def precise_wait_until(deadline: float) -> None:
  # 斩波要亚毫秒精度：先 sleep 到截止前 2 ms，再忙等
  remaining = deadline - time.perf_counter()
  if remaining > 0.002:
    time.sleep(remaining - 0.002)
  while time.perf_counter() < deadline:
    pass


def play_sound(sound: BuzzerSound, set_buzzer: Callable[[bool], None],
               wait_until: Callable[[float], None] = precise_wait_until, clock: Callable[[], float] = time.perf_counter) -> None:
  # 每次开关都对准从开始算起的绝对时刻：onroad 负载高时某次 sleep 睡过头，后面会追回来，总时长和斩波频率不漂
  t = clock()
  try:
    for segment in sound:
      if segment.chop_hz is None:
        set_buzzer(True)
        t += segment.on_seconds
        wait_until(t)
        set_buzzer(False)
      else:
        half_period = 0.5 / segment.chop_hz
        for _ in range(round(segment.on_seconds * segment.chop_hz)):
          set_buzzer(True)
          t += half_period
          wait_until(t)
          set_buzzer(False)
          t += half_period
          wait_until(t)
      t += segment.gap_seconds
      wait_until(t)
  finally:
    # 熄火时 manager 的 SIGINT 可能正好打断在响的时候，蜂鸣器不能卡在开着
    set_buzzer(False)


def open_buzzer_gpio() -> Callable[[bool], None] | None:
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
    return lambda on: os.write(value_fd, b"1" if on else b"0")
  cloudlog.error("buzzerd: siren gpio still not writable after 10 s, exiting so manager restarts and retries")
  return None


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
  # 1 kHz 斩波每 0.5 ms 开关一次，onroad 负载下被抢占会出毛刺；nice -10 实测满载时最长延迟从约 20 ms 降到个位数 ms。
  # 不用 SCHED_FIFO：放提醒音时整段都在忙等，会独占一个核
  os.nice(-10)
  set_buzzer = open_buzzer_gpio()
  if set_buzzer is None:
    return
  Buzzerd(lambda sound: play_sound(sound, set_buzzer)).buzzerd_thread()


if __name__ == "__main__":
  main()
