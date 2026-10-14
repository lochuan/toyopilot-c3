"""Chipmunk 一级设置面板（big UI / tici）：远程大模型开关（仅 offroad 可改）+ 手机 NPU 服务器地址。"""
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.sunnypilot.widgets.list_view import toggle_item_sp
from openpilot.system.ui.widgets import DialogResult, Widget
from openpilot.system.ui.widgets.keyboard import Keyboard
from openpilot.system.ui.widgets.list_view import button_item
from openpilot.system.ui.widgets.scroller_tici import Scroller


class ChipmunkLayout(Widget):
  def __init__(self):
    super().__init__()
    self._host_keyboard = Keyboard(min_text_size=0)
    self._bigmodel_toggle = toggle_item_sp(
      tr("Chipmunk"),
      tr("Use the phone NPU for the remote big model. Enable this while offroad, then start the phone app."),
      param="BigmodelToggle",
      enabled=lambda: ui_state.is_offroad(),
    )
    self._host_btn = button_item(
      tr("Chipmunk Server"),
      tr("EDIT"),
      tr("Phone NPU server address. Leave empty to discover it automatically."),
      callback=self._edit_host,
    )
    self._scroller = Scroller([self._bigmodel_toggle, self._host_btn], line_separator=True, spacing=0)

  def _edit_host(self):
    def update_host(result):
      if result != DialogResult.CONFIRM:
        return
      host = self._host_keyboard.text.strip()
      if host:
        ui_state.params.put("BigmodelServerHost", host, block=True)
      else:
        ui_state.params.remove("BigmodelServerHost")

    current = ui_state.params.get("BigmodelServerHost") or ""
    self._host_keyboard.reset(min_text_size=0)
    self._host_keyboard.set_title(tr("Chipmunk Server"), tr("Enter the phone IP, or leave empty for auto-discovery"))
    self._host_keyboard.set_text(current)
    self._host_keyboard.set_callback(update_host)
    gui_app.push_widget(self._host_keyboard)

  def _update_state(self):
    super()._update_state()
    # 每帧从参数同步：BigmodelToggle 可被 lanlinkd 远程改（同 mici 的 set_checked）
    self._bigmodel_toggle.action_item.set_state(ui_state.params.get_bool("BigmodelToggle"))
    host = ui_state.params.get("BigmodelServerHost") or tr("Auto-discover")
    self._host_btn.set_description(tr("Phone NPU server address. Current: ") + host)

  def _render(self, rect):
    self._scroller.render(rect)

  def show_event(self):
    self._scroller.show_event()
