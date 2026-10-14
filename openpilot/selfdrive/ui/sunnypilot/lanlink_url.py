"""LANLink 服务地址（纯逻辑，无 UI 依赖）：mici 与 big UI 两个 LANLink 设置页共用。"""
import socket

from openpilot.system.ui.lib.multilang import tr

LANLINK_PORT = 8088
IP_REFRESH_INTERVAL_S = 2.0


def get_lan_ip() -> str | None:
  """主网卡 IP：UDP connect 不产生真实流量，仅让内核选出接口。"""
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  try:
    s.connect(("8.8.8.8", 80))
    return s.getsockname()[0]
  except OSError:
    return None
  finally:
    s.close()


def lanlink_url_text(enabled: bool, ip: str | None) -> str:
  """服务地址显示文本：关 → 已禁用；开 + 有 IP → http://IP:端口；开 + 无 IP → —。"""
  if not enabled:
    return tr("service disabled")
  return f"http://{ip}:{LANLINK_PORT}" if ip else "—"


def current_lanlink_url_text(enabled: bool) -> str:
  """当前服务地址显示文本；关着时不探测 IP。"""
  return lanlink_url_text(enabled, get_lan_ip() if enabled else None)
