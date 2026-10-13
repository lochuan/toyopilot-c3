#!/usr/bin/env python3
"""
C3XL 板载蜂鸣器（GPIO.SIREN = 42）：C3XL 的提示音由这个蜂鸣器发出，soundd 的扬声器上听不到。
selfdriveState.alertSound 每次切换时响一次节奏：engage 1 声、disengage 2 声、其余提示 3 声。
移植自 jihulab mr-one/openpilot sn 分支 selfdrive/selfdrived/beep.py；那边每次开关 GPIO 都起一个 sudo tee（约 50 ms），
这里直接写 sysfs，把时长按 sn 实际听到的节奏补齐。
"""
import time
from collections.abc import Callable

from openpilot.cereal import log, messaging
from openpilot.common.gpio import gpio_export, gpio_set
from openpilot.common.hardware.comma.pins import GPIO
from openpilot.common.realtime import Ratekeeper
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.ui.soundd import check_selfdrive_timeout_alert
from openpilot.sunnypilot.selfdrive.ui.quiet_mode import QuietMode

AudibleAlert = log.SelfdriveState.AudibleAlert

SHORT_BEEP_SECONDS = 0.06  # 多声提示里每声的时长，也是声与声之间的间隔
# 提示音 → (响几声, 每声秒数)；表里没有的提示都按 WARNING_BEEP_PATTERN
BEEP_PATTERNS = {
  AudibleAlert.engage: (1, 0.1),
  AudibleAlert.disengage: (2, SHORT_BEEP_SECONDS),
}
WARNING_BEEP_PATTERN = (3, SHORT_BEEP_SECONDS)


def init_buzzer_gpio() -> None:
  gpio_export(GPIO.SIREN)
  # export 后 udev（99-gpio.rules）异步把权限交给 gpio 组，实测约 3 s；写失败就等它就绪再试，否则这次 onroad 全程不响
  for _ in range(200):
    try:
      with open(f"/sys/class/gpio/gpio{GPIO.SIREN}/direction", "w") as f:
        f.write("out")
      with open(f"/sys/class/gpio/gpio{GPIO.SIREN}/value", "w") as f:
        f.write("0")
      return
    except PermissionError:
      time.sleep(0.05)
  cloudlog.error("buzzerd: no permission to drive siren gpio")


class Buzzerd(QuietMode):
  def __init__(self, set_buzzer: Callable[[bool], None] | None = None, sleep: Callable[[float], None] = time.sleep):
    super().__init__()
    self.set_buzzer = set_buzzer or (lambda on: gpio_set(GPIO.SIREN, on))
    self.sleep = sleep
    self.current_alert = AudibleAlert.none

  def update_alert(self, new_alert: int) -> None:
    if new_alert == self.current_alert:
      return
    self.current_alert = new_alert
    if not self.should_play_sound(new_alert):
      return

    count, on_seconds = BEEP_PATTERNS.get(new_alert, WARNING_BEEP_PATTERN)
    for i in range(count):
      if i:
        self.sleep(SHORT_BEEP_SECONDS)
      self.set_buzzer(True)
      try:
        self.sleep(on_seconds)
      finally:
        # 熄火时 manager 的 SIGINT 可能正好打断在这里，蜂鸣器不能卡在开着
        self.set_buzzer(False)

  def update_from_messages(self, sm) -> None:
    if sm.updated['selfdriveState']:
      self.update_alert(sm['selfdriveState'].alertSound.raw)
    elif check_selfdrive_timeout_alert(sm):
      self.update_alert(AudibleAlert.warningImmediate)

  def buzzerd_thread(self) -> None:
    init_buzzer_gpio()
    sm = messaging.SubMaster(['selfdriveState', 'selfdriveStateSP'])
    rk = Ratekeeper(20)
    while True:
      sm.update(0)
      self.load_param()
      self.update_from_messages(sm)
      rk.keep_time()


def main():
  Buzzerd().buzzerd_thread()


if __name__ == "__main__":
  main()
