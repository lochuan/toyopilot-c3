from types import SimpleNamespace

import pytest

from openpilot.cereal import log
from openpilot.selfdrive.ui.buzzerd import (
  DISENGAGE_SOUND, ENGAGE_SOUND, PROMPT_SOUND, REFUSE_SOUND, WARNING_SOUND, BuzzerSegment, Buzzerd, play_sound,
)

AudibleAlert = log.SelfdriveState.AudibleAlert


def make_buzzerd_and_played_sounds(quiet_mode: bool = False) -> tuple[Buzzerd, list]:
  played_sounds: list = []
  buzzerd = Buzzerd(play_scene_sound=played_sounds.append)
  buzzerd.enabled = quiet_mode
  return buzzerd, played_sounds


@pytest.mark.parametrize("alert, sound", [
  (AudibleAlert.engage, ENGAGE_SOUND),
  (AudibleAlert.disengage, DISENGAGE_SOUND),
  (AudibleAlert.refuse, REFUSE_SOUND),
  (AudibleAlert.prompt, PROMPT_SOUND),
  (AudibleAlert.promptRepeat, PROMPT_SOUND),
  (AudibleAlert.promptDistracted, PROMPT_SOUND),
  (AudibleAlert.preAlert, PROMPT_SOUND),
  (AudibleAlert.warningSoft, WARNING_SOUND),
  (AudibleAlert.warningImmediate, WARNING_SOUND),
])
def test_each_alert_plays_its_scene_sound(alert, sound):
  buzzerd, played_sounds = make_buzzerd_and_played_sounds()
  buzzerd.update_alert(alert)
  assert played_sounds == [sound]


def test_scene_sounds_are_distinct():
  sounds = [ENGAGE_SOUND, DISENGAGE_SOUND, REFUSE_SOUND, PROMPT_SOUND, WARNING_SOUND]
  assert len(set(sounds)) == len(sounds)


def test_held_alert_plays_only_on_change():
  # EngagementAlert 持续 0.2 s，selfdriveState 会连续几帧带同一个 alertSound
  buzzerd, played_sounds = make_buzzerd_and_played_sounds()
  for alert in (AudibleAlert.none, AudibleAlert.engage, AudibleAlert.engage, AudibleAlert.engage, AudibleAlert.none):
    buzzerd.update_alert(alert)
  assert played_sounds == [ENGAGE_SOUND]


def test_quiet_mode_keeps_only_critical_alerts():
  buzzerd, played_sounds = make_buzzerd_and_played_sounds(quiet_mode=True)
  buzzerd.update_alert(AudibleAlert.engage)
  assert played_sounds == []
  buzzerd.update_alert(AudibleAlert.warningImmediate)
  assert played_sounds == [WARNING_SOUND]


class FakeSubMaster:
  def __init__(self, selfdrive_state_alert: int | None = None):
    # selfdrive_state_alert 为 None 表示这一帧没收到 selfdriveState
    self.updated = {'selfdriveState': selfdrive_state_alert is not None}
    self.alert_sound_raw = selfdrive_state_alert

  def __getitem__(self, service: str):
    return SimpleNamespace(alertSound=SimpleNamespace(raw=self.alert_sound_raw))


def test_selfdrive_state_timeout_plays_warning(mocker):
  # 同 soundd：selfdrived 掉线时补一个 warningImmediate
  mocker.patch("openpilot.selfdrive.ui.buzzerd.check_selfdrive_timeout_alert", return_value=True)
  buzzerd, played_sounds = make_buzzerd_and_played_sounds()
  buzzerd.update_from_messages(FakeSubMaster())
  assert played_sounds == [WARNING_SOUND]


def test_selfdrive_state_timeout_resets_so_next_warning_plays(mocker):
  # 掉线警告结束后要复位，selfdrived 恢复后的第一个 warningImmediate 不能被当成"没切换"吞掉
  timeout_alert = mocker.patch("openpilot.selfdrive.ui.buzzerd.check_selfdrive_timeout_alert", return_value=True)
  buzzerd, played_sounds = make_buzzerd_and_played_sounds()
  buzzerd.update_from_messages(FakeSubMaster())
  timeout_alert.return_value = False
  buzzerd.update_from_messages(FakeSubMaster())
  buzzerd.update_from_messages(FakeSubMaster(selfdrive_state_alert=AudibleAlert.warningImmediate))
  assert played_sounds == [WARNING_SOUND, WARNING_SOUND]


def play_sound_and_record_timeline(sound) -> list:
  # timeline：True/False = 蜂鸣器开/关，float = 等到的绝对时刻（从 0 开始，取 6 位小数免得浮点累加误差）
  timeline: list = []
  play_sound(sound, set_buzzer=timeline.append, wait_until=lambda deadline: timeline.append(round(deadline, 6)), clock=lambda: 0.)
  return timeline


def test_play_steady_segments_with_gaps():
  timeline = play_sound_and_record_timeline((BuzzerSegment(0.06, None, 0.05), BuzzerSegment(0.06, None, 0.)))
  assert timeline == [True, 0.06, False, 0.11, True, 0.17, False, 0.17, False]


def test_play_chopped_segment_toggles_at_chop_frequency():
  timeline = play_sound_and_record_timeline((BuzzerSegment(0.05, 80, 0.),))
  half_period = 0.5 / 80
  expected: list = []
  for k in range(4):
    expected += [True, round((2 * k + 1) * half_period, 6), False, round((2 * k + 2) * half_period, 6)]
  assert timeline == expected + [0.05, False]


def test_buzzer_turns_off_when_interrupted_mid_sound():
  # 熄火时 manager 用 SIGINT 停进程，正好打断在响的时候，蜂鸣器不能卡在开着
  buzzer_writes: list[bool] = []

  def interrupted_wait_until(deadline: float) -> None:
    raise KeyboardInterrupt

  with pytest.raises(KeyboardInterrupt):
    play_sound(DISENGAGE_SOUND, set_buzzer=buzzer_writes.append, wait_until=interrupted_wait_until)
  assert buzzer_writes == [True, False]
