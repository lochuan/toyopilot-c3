import pytest

from openpilot.selfdrive.ui.sunnypilot.nav_card import (
  Arrow, CardKind, NavIcon, INVALID_U32, card_content, format_distance, format_minutes, is_fresh, nav_icon,
)
from openpilot.selfdrive.ui.sunnypilot.nav_arrow_shapes import arrow_shape


def card(status="navigating", **overrides):
  values = {"has_nav_state": True, "status": status, "maneuver_type": 10, "distance_to_maneuver_m": 350,
            "route_remaining_m": 12400, "route_remaining_s": 1080, "roundabout_exit_index": 0,
            "is_metric": True, "arrived_card_visible": True}
  values.update(overrides)
  return card_content(**values)


def test_navigation_guidance_and_invalid_fields():
  content = card()
  assert (content.arrow, content.distance_text, content.time_text, content.remaining_text) == (Arrow.RIGHT, "350 m", "18 min", "12.4 km")
  assert card(distance_to_maneuver_m=INVALID_U32).distance_text is None
  assert card(maneuver_type=255).arrow is None
  assert card(maneuver_type=26, roundabout_exit_index=3).exit_index == 3
  assert card(maneuver_type=255, distance_to_maneuver_m=INVALID_U32,
              route_remaining_m=INVALID_U32, route_remaining_s=INVALID_U32).kind == CardKind.OFF_ROUTE


@pytest.mark.parametrize("status, kind", [("rerouting", CardKind.REROUTING), ("positionLost", CardKind.POSITION_LOST), ("arrived", CardKind.ARRIVED)])
def test_status_cards_discard_old_guidance(status, kind):
  content = card(status)
  assert content.kind == kind
  assert content.distance_text is None and content.time_text is None and content.remaining_text is None
  assert card("arrived", arrived_card_visible=False) is None


def test_missing_inactive_and_error_statuses():
  assert card(has_nav_state=False) is None
  for status in ("notRunning", "idle", "mapMissing", "fault"):
    assert card(status) is None
  assert nav_icon(True, "navigating") == NavIcon.GREEN
  assert nav_icon(True, "positionLost") == NavIcon.SLASHED
  assert nav_icon(False, "navigating") == NavIcon.HIDDEN


def test_distance_units_rounding_and_limits():
  assert format_distance(995, True) == "1.0 km"
  assert format_distance(60, False) == "200 ft"
  assert format_distance(1609, False) == "1.0 mi"
  assert format_distance(1_000_000, True) == "999+ km"
  assert format_minutes(0) == "1 min"
  assert format_minutes(360000) == "99+ h"


def test_freshness_boundary_and_missing_message():
  assert is_fresh(12.0, 10.0, True)
  assert not is_fresh(12.001, 10.0, True)
  assert not is_fresh(10.0, 10.0, False)


def test_all_supported_arrows_have_geometry():
  for arrow in Arrow:
    shape = arrow_shape(arrow)
    assert shape.polylines or shape.ring or shape.pin
  assert arrow_shape(Arrow.ROUNDABOUT).ring
  assert arrow_shape(Arrow.ARRIVE).pin
