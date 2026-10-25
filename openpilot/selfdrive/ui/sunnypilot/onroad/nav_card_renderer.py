"""C3XL big-UI navigation overlay; messages update content, frames only draw cached text/geometry."""
import time

import pyray as rl

from openpilot.selfdrive.ui.sunnypilot.nav_arrow_shapes import arrow_shape
from openpilot.selfdrive.ui.sunnypilot.nav_card import (
  Arrow, CardContent, CardKind, NavIcon, FRESH_SECONDS, arrived_visible, card_content, is_fresh, nav_icon,
)
from openpilot.selfdrive.ui.sunnypilot.onroad.developer_ui import get_bottom_dev_ui_offset
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import FONT_SCALE, FontWeight, gui_app
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.lib.wrap_text import wrap_text

ACCENT = rl.Color(155, 230, 185, 255)
MUTED = rl.Color(162, 175, 185, 255)
DIM = rl.Color(92, 104, 112, 255)
RED = rl.Color(210, 90, 90, 255)
GRAY = rl.Color(110, 118, 125, 255)
WHITE = rl.WHITE
CARD_BACKGROUND = rl.Color(7, 13, 18, 230)
BLOCK_BACKGROUND = rl.Color(255, 255, 255, 23)
PIN_FILL = rl.Color(7, 13, 18, 255)
CARD_WIDTH = 540
CARD_HEIGHT = 250
SHORT_CARD_HEIGHT = 150
TEXT_LEFT = 158
ARROW_SIZE = 110
EXIT_FONT_SIZE = 30
ICON_SIZE = 72
PHRASE_FONT_SIZE = 44


def _rounded(rect: rl.Rectangle, radius: float, color: rl.Color) -> None:
  rl.draw_rectangle_rounded(rect, 2 * radius / min(rect.width, rect.height), 8, color)


def _draw_polyline(points: list[rl.Vector2], thickness: float, color: rl.Color) -> None:
  for a, b in zip(points, points[1:], strict=False):
    rl.draw_line_ex(a, b, thickness, color)
  for p in points:
    rl.draw_circle_v(p, thickness / 2, color)


class NavCardRenderer:
  def __init__(self):
    self._bold = gui_app.font(FontWeight.BOLD)
    self._medium = gui_app.font(FontWeight.MEDIUM)
    self._content: CardContent | None = None
    self._icon = NavIcon.HIDDEN
    self._arrived_since: float | None = None
    self._started_frame = -1
    self._is_metric = ui_state.is_metric
    self._phrase_lines: list[str] = []
    self._summary: list[tuple[str, float, rl.Color]] = []
    self._distance_size = 76
    self._summary_size = 44

  def update(self) -> None:
    sm = ui_state.sm
    if not ui_state.started or self._started_frame != ui_state.started_frame:
      self._content = None
      self._icon = NavIcon.HIDDEN
      self._arrived_since = None
      self._started_frame = ui_state.started_frame
    if not ui_state.started or not sm.valid['navStateSP'] or sm.recv_frame['navStateSP'] < ui_state.started_frame:
      return
    if sm.updated['navStateSP'] or self._is_metric != ui_state.is_metric:
      self._on_message(sm['navStateSP'], sm.recv_time['navStateSP'])

  def _on_message(self, message, received_at: float) -> None:
    nav = message.navState
    status = str(nav.status)
    if status in ("navigating", "rerouting") and not message.phoneLocationOk:
      status = "positionLost"
    if message.hasNavState and status == "arrived":
      if self._arrived_since is None:
        self._arrived_since = received_at
    else:
      self._arrived_since = None
    self._is_metric = ui_state.is_metric
    self._icon = nav_icon(message.hasNavState, status)
    self._content = card_content(
      has_nav_state=message.hasNavState, status=status, maneuver_type=nav.maneuverType,
      distance_to_maneuver_m=nav.distanceToManeuverM, route_remaining_m=nav.routeRemainingM,
      route_remaining_s=nav.routeRemainingSeconds, roundabout_exit_index=nav.roundaboutExitIndex,
      is_metric=self._is_metric, arrived_card_visible=True)
    content = self._content
    self._phrase_lines = wrap_text(self._bold, content.phrase, PHRASE_FONT_SIZE, CARD_WIDTH - TEXT_LEFT - 24) if content and content.phrase else []
    self._distance_size = 76
    if content and content.distance_text:
      width = measure_text_cached(self._bold, content.distance_text, 76).x
      self._distance_size = min(76, int(76 * (CARD_WIDTH - TEXT_LEFT - 24) / max(width, 1)))
    self._summary = []
    if content:
      values = [(text, color) for text, color in ((content.time_text, ACCENT), (content.remaining_text, MUTED)) if text is not None]
      widths = [measure_text_cached(self._medium, text, 44).x for text, _ in values]
      available = CARD_WIDTH - 48 - 28 * len(values) - 16 * max(0, len(values) - 1)
      self._summary_size = min(44, int(44 * available / max(sum(widths), 1)))
      self._summary = [(text, measure_text_cached(self._medium, text, self._summary_size).x + 28, color) for text, color in values]

  def _fresh(self) -> bool:
    sm = ui_state.sm
    if not ui_state.started or not sm.valid['navStateSP'] or sm.recv_frame['navStateSP'] < ui_state.started_frame:
      return False
    now = time.monotonic()
    if not is_fresh(now, sm.recv_time['navStateSP'], sm.seen['navStateSP']):
      return False
    message = sm['navStateSP']
    if message.hasNavState and message.phoneLocationOk and str(message.navState.status) in ("navigating", "rerouting"):
      return message.navState.ageMs / 1000 + now - sm.recv_time['navStateSP'] <= FRESH_SECONDS
    return True

  def icon(self) -> NavIcon:
    return self._icon if self._fresh() else NavIcon.HIDDEN

  def card(self) -> CardContent | None:
    if not self._fresh():
      return None
    if self._content and self._content.kind == CardKind.ARRIVED:
      if self._arrived_since is None or not arrived_visible(int(self._arrived_since * 1e9), int(time.monotonic() * 1e9)):
        return None
    return self._content

  def render_icon(self, rect: rl.Rectangle) -> None:
    """紧邻现有 NPU 上方，与其水平居中；跟随底部开发者栏上移。"""
    form = self.icon()
    if form == NavIcon.HIDDEN:
      return
    scale = ICON_SIZE / 24
    left = rect.x + rect.width - 42 - 108 / 2 - ICON_SIZE / 2
    top = rect.y + rect.height - 28 - get_bottom_dev_ui_offset() - 80 - 18 - ICON_SIZE

    def pt(x: float, y: float) -> rl.Vector2:
      return rl.Vector2(left + x * scale, top + y * scale)

    color = ACCENT if form == NavIcon.GREEN else GRAY
    outline = [pt(12, 2), pt(20, 21), pt(12, 16.5), pt(4, 21), pt(12, 2)]
    _draw_polyline(outline, 2 * scale, color)
    if form == NavIcon.GREEN:
      rl.draw_circle_v(pt(19, 5), 4.2 * scale, rl.BLACK)
      rl.draw_ring(pt(19, 5), (4.2 - 0.8) * scale, (4.2 + 0.8) * scale, 0.0, 360.0, 16, color)
      _draw_polyline([pt(17, 5), pt(18.5, 6.6), pt(21.1, 3.6)], 1.6 * scale, color)
    else:
      _draw_polyline([pt(3, 3), pt(21, 21)], 2 * scale, RED)

  def render_card(self, rect: rl.Rectangle) -> None:
    content = self.card()
    if content is None:
      return
    x, y = rect.x + rect.width - 42 - CARD_WIDTH, rect.y + 30
    short = content.kind != CardKind.NAVIGATING
    height = max(SHORT_CARD_HEIGHT, len(self._phrase_lines) * PHRASE_FONT_SIZE * FONT_SCALE + 48) if short else CARD_HEIGHT
    _rounded(rl.Rectangle(x, y, CARD_WIDTH, height), 32, CARD_BACKGROUND)
    if not short:
      if content.arrow is not None:
        self._draw_arrow(content.arrow, x + 24, y + 24, ACCENT, content.exit_index)
      if content.distance_text:
        self._text(self._bold, content.distance_text, x + TEXT_LEFT, y + 40, self._distance_size, WHITE)
      cursor = x + 24
      for text, width, color in self._summary:
        _rounded(rl.Rectangle(cursor, y + 170, width, 56), 14, BLOCK_BACKGROUND)
        self._text(self._medium, text, cursor + 14, y + 170 + (56 - self._summary_size * FONT_SCALE) / 2, self._summary_size, color)
        cursor += width + 16
    else:
      lost = content.kind == CardKind.POSITION_LOST
      self._draw_arrow(Arrow.ARRIVE if content.kind == CardKind.ARRIVED else Arrow.STRAIGHT, x + 24, y + 20,
                       ACCENT if content.kind == CardKind.ARRIVED else DIM, 0)
      if lost:
        _draw_polyline([rl.Vector2(x + 40, y + 110), rl.Vector2(x + 120, y + 40)], 9, RED)
      line_height = PHRASE_FONT_SIZE * FONT_SCALE
      top = y + (height - len(self._phrase_lines) * line_height) / 2
      for line in self._phrase_lines:
        self._text(self._bold, line, x + TEXT_LEFT, top, PHRASE_FONT_SIZE,
                   RED if lost else WHITE if content.kind == CardKind.ARRIVED else MUTED)
        top += line_height

  @staticmethod
  def _text(font: rl.Font, text: str, x: float, y: float, size: int, color: rl.Color) -> None:
    rl.draw_text_ex(font, text, rl.Vector2(x, y), size, 0, color)

  def _draw_arrow(self, arrow: Arrow, left: float, top: float, color: rl.Color, exit_index: int) -> None:
    scale = ARROW_SIZE / 60
    shape = arrow_shape(arrow)

    def pt(point: tuple[float, float]) -> rl.Vector2:
      return rl.Vector2(left + (31 + 1.4 * point[0]) * scale, top + (30 + 1.4 * point[1]) * scale)

    ghost_color = rl.Color(color.r, color.g, color.b, 97)
    for line in shape.ghost:
      _draw_polyline([pt(p) for p in line], 7 * scale, ghost_color)
    if shape.ring is not None:
      center = pt((shape.ring[0], shape.ring[1]))
      radius = shape.ring[2] * 1.4 * scale
      rl.draw_ring(center, radius - 2.5 * scale, radius + 2.5 * scale, 0.0, 360.0, 24, rl.Color(color.r, color.g, color.b, 128))
      if exit_index > 0:
        text = str(exit_index)
        half_width = measure_text_cached(self._bold, text, EXIT_FONT_SIZE).x / 2
        self._text(self._bold, text, center.x - half_width, center.y - EXIT_FONT_SIZE * FONT_SCALE / 2, EXIT_FONT_SIZE, color)
    if shape.pin:
      center = pt((0, -4))
      _draw_polyline([pt((-6.5, 2)), pt((0, 13)), pt((6.5, 2))], 7 * scale, color)
      rl.draw_circle_v(center, 8 * 1.4 * scale + 3.5 * scale, color)
      rl.draw_circle_v(center, 8 * 1.4 * scale - 3.5 * scale, PIN_FILL)
      rl.draw_circle_v(center, 4 * scale, color)
    for line in shape.polylines:
      _draw_polyline([pt(p) for p in line], 7 * scale, color)
