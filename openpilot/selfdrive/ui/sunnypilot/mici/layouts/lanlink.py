"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import time

import pyray as rl

from openpilot.selfdrive.ui.mici.widgets.button import BigToggle
from openpilot.selfdrive.ui.sunnypilot.lanlink_url import IP_REFRESH_INTERVAL_S, current_lanlink_url_text
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import FontWeight
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.label import UnifiedLabel
from openpilot.system.ui.widgets.scroller import NavScroller

class LanLinkInfo(Widget):
  def __init__(self):
    super().__init__()
    self.set_rect(rl.Rectangle(0, 0, 360, 100))

    header_color = rl.Color(255, 255, 255, int(255 * 0.9))
    subheader_color = rl.Color(255, 255, 255, int(255 * 0.9 * 0.65))
    max_width = int(self._rect.width - 20)
    self.url_header = UnifiedLabel(tr("service url"), 48, max_width=max_width, text_color=header_color,
                                   font_weight=FontWeight.DISPLAY, shimmer=True)
    self.url_text = UnifiedLabel("—", 32, max_width=max_width, text_color=subheader_color,
                                 font_weight=FontWeight.ROMAN, scroll=True)

  def _render(self, _):
    self.url_header.set_position(self._rect.x + 20, self._rect.y - 10)
    self.url_header.render()

    self.url_text.set_position(self._rect.x + 20, self._rect.y + 68 - 25)
    self.url_text.render()


class LanLinkLayoutMici(NavScroller):
  def __init__(self):
    super().__init__()
    self._url: str = "—"
    self._last_ip_refresh = 0.0

    self._lanlink_info = LanLinkInfo()
    self._lanlink_toggle = BigToggle(text=tr("enable lanlink"),
                                     initial_state=ui_state.params.get_bool("LanLinkEnabled"),
                                     toggle_callback=self._lanlink_toggle_callback)

    self._scroller.add_widgets([
      self._lanlink_info,
      self._lanlink_toggle,
    ])

    self._refresh_url()

  def _refresh_url(self):
    self._url = current_lanlink_url_text(ui_state.params.get_bool("LanLinkEnabled"))

  def _update_state(self):
    super()._update_state()
    self._lanlink_toggle.set_checked(ui_state.params.get_bool("LanLinkEnabled"))
    now = time.monotonic()
    if now - self._last_ip_refresh >= IP_REFRESH_INTERVAL_S:
      self._last_ip_refresh = now
      self._refresh_url()
    self._lanlink_info.url_text.set_text(self._url)

  def show_event(self):
    super().show_event()
    ui_state.update_params()
    self._refresh_url()

  @staticmethod
  def _lanlink_toggle_callback(state: bool):
    ui_state.params.put_bool("LanLinkEnabled", state)
    ui_state.update_params()
