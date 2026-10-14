from openpilot.selfdrive.ui.sunnypilot.lanlink_url import lanlink_url_text


def test_lanlink_url_text_disabled_shows_service_disabled():
  assert lanlink_url_text(False, "10.0.0.44") == "service disabled"


def test_lanlink_url_text_enabled_shows_lanlink_url():
  assert lanlink_url_text(True, "10.0.0.44") == "http://10.0.0.44:8088"


def test_lanlink_url_text_enabled_without_ip_shows_dash():
  assert lanlink_url_text(True, None) == "—"


def test_current_lanlink_url_text_skips_ip_probe_when_disabled(monkeypatch):
  import openpilot.selfdrive.ui.sunnypilot.lanlink_url as lanlink_url

  def fail_probe():
    raise AssertionError("关着时不该探测 IP")
  monkeypatch.setattr(lanlink_url, "get_lan_ip", fail_probe)
  assert lanlink_url.current_lanlink_url_text(False) == "service disabled"
