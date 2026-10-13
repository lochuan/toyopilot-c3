import pytest

from openpilot.cereal import log
from openpilot.selfdrive.ui.buzzerd import Buzzerd

AudibleAlert = log.SelfdriveState.AudibleAlert

# 预期的蜂鸣器时间线：True/False = 蜂鸣器开/关，float = sleep 秒数
ENGAGE_TIMELINE = [True, 0.1, False]
DISENGAGE_TIMELINE = [True, 0.06, False, 0.06, True, 0.06, False]
WARNING_TIMELINE = [True, 0.06, False, 0.06, True, 0.06, False, 0.06, True, 0.06, False]


def make_buzzerd_and_timeline(quiet_mode: bool = False) -> tuple[Buzzerd, list]:
  timeline: list = []
  buzzerd = Buzzerd(set_buzzer=timeline.append, sleep=timeline.append)
  buzzerd.enabled = quiet_mode
  return buzzerd, timeline


def test_engage_beeps_once():
  buzzerd, timeline = make_buzzerd_and_timeline()
  buzzerd.update_alert(AudibleAlert.engage)
  assert timeline == ENGAGE_TIMELINE


def test_disengage_beeps_twice():
  buzzerd, timeline = make_buzzerd_and_timeline()
  buzzerd.update_alert(AudibleAlert.disengage)
  assert timeline == DISENGAGE_TIMELINE


def test_warnings_beep_three_times():
  for alert in (AudibleAlert.refuse, AudibleAlert.prompt, AudibleAlert.warningSoft, AudibleAlert.warningImmediate):
    buzzerd, timeline = make_buzzerd_and_timeline()
    buzzerd.update_alert(alert)
    assert timeline == WARNING_TIMELINE, alert


def test_held_alert_beeps_only_on_change():
  # EngagementAlert 持续 0.2 s，selfdriveState 会连续几帧带同一个 alertSound
  buzzerd, timeline = make_buzzerd_and_timeline()
  for alert in (AudibleAlert.none, AudibleAlert.engage, AudibleAlert.engage, AudibleAlert.engage, AudibleAlert.none):
    buzzerd.update_alert(alert)
  assert timeline == ENGAGE_TIMELINE


def test_quiet_mode_keeps_only_critical_alerts():
  buzzerd, timeline = make_buzzerd_and_timeline(quiet_mode=True)
  buzzerd.update_alert(AudibleAlert.engage)
  assert timeline == []
  buzzerd.update_alert(AudibleAlert.warningImmediate)
  assert timeline == WARNING_TIMELINE


def test_buzzer_turns_off_when_interrupted_mid_beep():
  # 熄火时 manager 用 SIGINT 停进程，正好打断在响的时候，蜂鸣器不能卡在开着
  buzzer_writes: list[bool] = []

  def interrupted_sleep(seconds: float) -> None:
    raise KeyboardInterrupt

  buzzerd = Buzzerd(set_buzzer=buzzer_writes.append, sleep=interrupted_sleep)
  buzzerd.enabled = False
  with pytest.raises(KeyboardInterrupt):
    buzzerd.update_alert(AudibleAlert.disengage)
  assert buzzer_writes == [True, False]


class FakeSubMaster:
  def __init__(self, updated_services: set[str]):
    self.updated = {'selfdriveState': 'selfdriveState' in updated_services}


def test_selfdrive_state_timeout_beeps_warning(mocker):
  # 同 soundd：selfdrived 掉线时补一个 warningImmediate
  mocker.patch("openpilot.selfdrive.ui.buzzerd.check_selfdrive_timeout_alert", return_value=True)
  buzzerd, timeline = make_buzzerd_and_timeline()
  buzzerd.update_from_messages(FakeSubMaster(updated_services=set()))
  assert timeline == WARNING_TIMELINE
