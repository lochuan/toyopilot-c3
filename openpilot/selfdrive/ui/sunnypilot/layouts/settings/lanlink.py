"""LANLink 一级设置面板（big UI / tici）：开关 + 服务地址，口径同 C4 mici 的 LanLinkLayoutMici。"""
import time

from openpilot.selfdrive.ui.sunnypilot.lanlink_url import IP_REFRESH_INTERVAL_S, current_lanlink_url_text
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.sunnypilot.widgets.list_view import toggle_item_sp
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.list_view import text_item
from openpilot.system.ui.widgets.scroller_tici import Scroller


class LanLinkLayout(Widget):
  def __init__(self):
    super().__init__()
    self._url = "—"
    self._url_enabled: bool | None = None  # 上次算地址时的开关值；变了立即重算
    self._last_url_refresh = 0.0
    self._toggle = toggle_item_sp(lambda: tr("enable lanlink"), param="LanLinkEnabled")
    self._scroller = Scroller([
      self._toggle,
      text_item(lambda: tr("service url"), lambda: self._url),
    ], line_separator=True, spacing=0)

  def _refresh_url(self, enabled: bool):
    self._url_enabled = enabled
    self._last_url_refresh = time.monotonic()
    self._url = current_lanlink_url_text(enabled)

  def _update_state(self):
    super()._update_state()
    # 开关回调先于参数写入，故每帧从参数同步；外部改参数（ssh）也能跟上
    enabled = ui_state.params.get_bool("LanLinkEnabled")
    self._toggle.action_item.set_state(enabled)
    if enabled != self._url_enabled or time.monotonic() - self._last_url_refresh >= IP_REFRESH_INTERVAL_S:
      self._refresh_url(enabled)

  def _render(self, rect):
    self._scroller.render(rect)

  def show_event(self):
    self._scroller.show_event()
    self._refresh_url(ui_state.params.get_bool("LanLinkEnabled"))
