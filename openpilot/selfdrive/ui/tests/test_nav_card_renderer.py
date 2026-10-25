"""Headless checks at the renderer interface; font and UI state are the test adapters."""
import importlib
import sys
from types import SimpleNamespace

import pyray as rl
import pytest

from openpilot.selfdrive.ui.sunnypilot.nav_card import CardKind, NavIcon


@pytest.fixture
def navigation(monkeypatch):
  message = SimpleNamespace(hasNavState=True, phoneLocationOk=True, navState=SimpleNamespace(
    status="navigating", maneuverType=10, distanceToManeuverM=350, routeRemainingM=12400,
    routeRemainingSeconds=1080, roundaboutExitIndex=0, ageMs=50))
  subscriber = {"navStateSP": message}

  class Subscriber(dict):
    updated = {"navStateSP": True}
    recv_time = {"navStateSP": 10.0}
    recv_frame = {"navStateSP": 10}
    seen = {"navStateSP": True}
    valid = {"navStateSP": True}

  state = SimpleNamespace(started=True, started_frame=10, is_metric=True, sm=Subscriber(subscriber))
  font = SimpleNamespace(texture=SimpleNamespace(id=1))
  monkeypatch.setitem(sys.modules, "openpilot.selfdrive.ui.ui_state", SimpleNamespace(ui_state=state))
  monkeypatch.setitem(sys.modules, "openpilot.system.ui.lib.application", SimpleNamespace(
    gui_app=SimpleNamespace(font=lambda _: font), FontWeight=SimpleNamespace(BOLD=0, MEDIUM=1),
    FONT_SCALE=1.16, font_fallback=lambda font: font))
  monkeypatch.setitem(sys.modules, "openpilot.system.ui.lib.text_measure", SimpleNamespace(
    measure_text_cached=lambda font, text, size, spacing=0: rl.Vector2(len(text) * size * .6, size * 1.16)))
  monkeypatch.setitem(sys.modules, "openpilot.selfdrive.ui.sunnypilot.onroad.developer_ui", SimpleNamespace(get_bottom_dev_ui_offset=lambda: 0))
  name = "openpilot.selfdrive.ui.sunnypilot.onroad.nav_card_renderer"
  module = importlib.import_module(name)
  clock = SimpleNamespace(now=10.0)
  monkeypatch.setattr(module.time, "monotonic", lambda: clock.now)
  renderer = module.NavCardRenderer()
  renderer.update()
  yield renderer, state, message, clock
  sys.modules.pop(name, None)
  sys.modules.pop("openpilot.system.ui.lib.wrap_text", None)


def test_guidance_expires_and_rejects_previous_drive(navigation):
  renderer, state, message, clock = navigation
  assert renderer.card().distance_text == "350 m"
  clock.now = 12.001
  assert renderer.card() is None and renderer.icon() == NavIcon.HIDDEN
  clock.now = 10.0
  state.started_frame = 11
  renderer.update()
  assert renderer.card() is None
  state.started = False
  assert renderer.icon() == NavIcon.HIDDEN


def test_phone_location_and_source_age_never_leave_old_turn(navigation):
  renderer, state, message, clock = navigation
  message.phoneLocationOk = False
  renderer.update()
  assert renderer.card().kind == CardKind.POSITION_LOST
  assert renderer.icon() == NavIcon.SLASHED
  message.phoneLocationOk = True
  message.navState.ageMs = 2001
  renderer.update()
  assert renderer.card() is None
  message.navState.ageMs = 1500
  clock.now = 10.6
  renderer.update()
  assert renderer.card() is None


def test_arrival_timeout_and_cached_unit_change(navigation):
  renderer, state, message, clock = navigation
  state.is_metric = False
  state.sm.updated["navStateSP"] = False
  renderer.update()
  assert renderer.card().distance_text == "0.2 mi"
  message.navState.status = "arrived"
  state.sm.updated["navStateSP"] = True
  renderer.update()
  assert renderer.card().kind == CardKind.ARRIVED
  clock.now = 15.0
  state.sm.recv_time["navStateSP"] = 15.0
  renderer.update()
  assert renderer.card() is None


def test_invalid_messages_and_missing_state_hide_guidance(navigation):
  renderer, state, message, clock = navigation
  state.sm.valid["navStateSP"] = False
  assert renderer.card() is None and renderer.icon() == NavIcon.HIDDEN
  state.sm.valid["navStateSP"] = True
  message.hasNavState = False
  renderer.update()
  assert renderer.card() is None and renderer.icon() == NavIcon.HIDDEN


def test_hidden_mode_button_cancels_touches_without_toggling(navigation, monkeypatch):
  _, state, _, _ = navigation
  application = sys.modules["openpilot.system.ui.lib.application"]
  application.MAX_TOUCH_SLOTS = 1
  application.MousePos = application.MouseEvent = SimpleNamespace
  application.gui_app.show_touches = False
  application.gui_app.texture = lambda *args: SimpleNamespace(width=144, height=144)
  state.has_longitudinal_control = True
  state.sm["selfdriveState"] = SimpleNamespace(experimentalMode=False, engageable=True, enabled=True)
  changes, draws = [], []
  params = SimpleNamespace(get_bool=lambda key: True, put_bool=lambda key, value: changes.append((key, value)))
  monkeypatch.setitem(sys.modules, "openpilot.common.params", SimpleNamespace(Params=lambda: params))
  monkeypatch.setattr(rl, "draw_circle", lambda *args: draws.append("button"))
  monkeypatch.setattr(rl, "draw_texture_ex", lambda *args: None)
  try:
    from openpilot.selfdrive.ui.onroad.exp_button import ExpButton
    button = ExpButton(192, 144)
    rect = rl.Rectangle(300, 81, 192, 192)

    def frame(pressed=False, released=False):
      application.gui_app.mouse_events = [SimpleNamespace(slot=0, pos=rl.Vector2(396, 177), left_pressed=pressed, left_released=released)]
      button.render(rect)

    frame(pressed=True)
    assert button.is_pressed
    button.set_enabled(False)
    draws.clear()
    frame()
    assert not draws and not button.is_pressed
    frame(pressed=True)
    frame(released=True)
    assert not changes
    button.set_enabled(True)
    frame(released=True)
    assert not changes
    frame(pressed=True)
    frame(released=True)
    assert changes == [("ExperimentalMode", True)]
  finally:
    sys.modules.pop("openpilot.selfdrive.ui.onroad.exp_button", None)
    sys.modules.pop("openpilot.system.ui.widgets", None)
