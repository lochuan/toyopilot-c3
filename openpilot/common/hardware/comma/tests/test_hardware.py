import subprocess

from openpilot.common.hardware.comma import hardware
from openpilot.common.hardware.comma.hardware import HardwareComma


def run_set_power_save(mocker, wlan_rx_pids):
  mocker.patch.object(HardwareComma, "amplifier", None)
  mocker.patch.object(hardware, "sudo_write")
  mocker.patch.object(hardware, "get_irqs_for_action", return_value=[])

  def fake_run(cmd, **kwargs):
    if cmd[:2] == ["pgrep", "-x"]:
      stdout = "".join(f"{pid}\n" for pid in wlan_rx_pids) if cmd[2] == "cds_ol_rx_threa" else ""
      return subprocess.CompletedProcess(cmd, 0 if stdout else 1, stdout=stdout, stderr="")
    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

  run = mocker.patch.object(hardware.subprocess, "run", side_effect=fake_run)
  HardwareComma().set_power_save(False)
  return [c.args[0] for c in run.call_args_list if c.args[0][:2] == ["sudo", "taskset"]]


class TestSetPowerSave:
  def test_pins_wlan_rx_thread_to_camerad_core(self, mocker):
    assert run_set_power_save(mocker, [48853]) == [["sudo", "taskset", "-pc", "6", "48853"]]

  def test_skips_silently_when_wlan_rx_thread_missing(self, mocker):
    assert run_set_power_save(mocker, []) == []
