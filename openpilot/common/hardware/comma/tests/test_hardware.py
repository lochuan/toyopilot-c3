import subprocess
from unittest.mock import mock_open

import pytest

from openpilot.common.hardware.comma import hardware
from openpilot.common.hardware.comma.hardware import HardwareComma

WLAN_RX_PID = "48853"


class FakeWlanRxThread:
  def __init__(self, mocker, alive=True, cpus_allowed="7", failing_step=None, error: Exception | None = None):
    self.alive = alive
    self.cpus_allowed = cpus_allowed
    self.failing_step, self.error = failing_step, error
    self.taskset_calls = []
    mocker.patch.object(hardware.subprocess, "run", side_effect=self.run)
    mocker.patch.object(hardware, "open", side_effect=self.open, create=True)

  def run(self, cmd, **kwargs):
    assert kwargs.get("timeout"), f"{cmd} must not block hardwared"
    if self.error and (self.failing_step == cmd[0] or (self.failing_step == "taskset" and cmd[:2] == ["sudo", "taskset"])):
      raise self.error
    if cmd == ["pgrep", "-x", "cds_ol_rx_threa"]:
      stdout = f"{WLAN_RX_PID}\n" if self.alive else ""
      return subprocess.CompletedProcess(cmd, 0 if self.alive else 1, stdout=stdout, stderr="")
    if cmd[:2] == ["sudo", "taskset"]:
      self.taskset_calls.append(cmd)
    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

  def open(self, path, *args, **kwargs):
    assert path == f"/proc/{WLAN_RX_PID}/status"
    if self.error and self.failing_step == "status":
      raise self.error
    return mock_open(read_data=f"Name:\tcds_ol_rx_threa\nCpus_allowed:\t80\nCpus_allowed_list:\t{self.cpus_allowed}\n")()


class TestPinWlanRxThreadToCameradCore:
  def test_pins_thread_on_modeld_core(self, mocker):
    thread = FakeWlanRxThread(mocker, cpus_allowed="7")
    HardwareComma().pin_wlan_rx_thread_to_camerad_core()
    assert thread.taskset_calls == [["sudo", "taskset", "-pc", "6", WLAN_RX_PID]]

  def test_leaves_thread_already_on_camerad_core(self, mocker):
    thread = FakeWlanRxThread(mocker, cpus_allowed="6")
    HardwareComma().pin_wlan_rx_thread_to_camerad_core()
    assert thread.taskset_calls == []

  def test_pins_thread_that_starts_after_first_check(self, mocker):
    thread = FakeWlanRxThread(mocker, alive=False)
    hw = HardwareComma()
    hw.pin_wlan_rx_thread_to_camerad_core()
    assert thread.taskset_calls == []

    thread.alive = True
    hw.pin_wlan_rx_thread_to_camerad_core()
    assert thread.taskset_calls == [["sudo", "taskset", "-pc", "6", WLAN_RX_PID]]

  @pytest.mark.parametrize("failing_step, error", [
    ("pgrep", FileNotFoundError("pgrep")),
    ("pgrep", subprocess.TimeoutExpired("pgrep", 1)),
    ("status", FileNotFoundError("/proc/48853/status")),
    ("taskset", subprocess.TimeoutExpired("sudo", 1)),
  ])
  def test_errors_do_not_reach_hardwared(self, mocker, failing_step, error):
    FakeWlanRxThread(mocker, failing_step=failing_step, error=error)
    HardwareComma().pin_wlan_rx_thread_to_camerad_core()


class TestSetPowerSave:
  @pytest.fixture(autouse=True)
  def fake_hardware(self, mocker):
    mocker.patch.object(HardwareComma, "amplifier", None)
    mocker.patch.object(hardware, "sudo_write")
    mocker.patch.object(hardware, "get_irqs_for_action", return_value=[])

  def test_onroad_pins_wlan_rx_thread(self, mocker):
    thread = FakeWlanRxThread(mocker)
    HardwareComma().set_power_save(False)
    assert thread.taskset_calls == [["sudo", "taskset", "-pc", "6", WLAN_RX_PID]]
