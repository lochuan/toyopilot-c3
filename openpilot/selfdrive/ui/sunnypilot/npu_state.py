"""07 号：NPU 图标颜色规则（纯函数，无 UI 依赖）。

两套口径：
  - npu_color：mici 首页按链路状态（2026-09-30 用户拍板的二色）。
    开 + onroad + 已连上（BigmodelLinkState ∈ connected/blip/restart）：绿；开 + 其余：橙；关：不显示（调用方判断）。
    BigmodelLinkState 是 CLEAR_ON_MANAGER_START、offroad 保留上趟旧值，故必须按 started 门控；
    bigmodeld 进程启动时写一次 connecting，防新一趟起步读到上趟 connected 闪绿。
  - npu_icon：侧边栏与行车 HUD 按大模型参与率（BigFrameWindow，只在 ui_state.big_frames 统计一份）。
    关：灰；开 + 最近 50 帧 ≥45 帧大模型：绿；开 + 其余：橙。行车 HUD 只在绿时画图标。
"""
from collections import deque

LINK_CONNECTED = ("connected", "blip", "restart")  # 06 号链路状态串的「已连上」取值


def npu_color(started: bool, link_state: str) -> str:
  """"green" iff onroad 且链路已连上，其余一切 "orange"。"""
  return "green" if started and link_state in LINK_CONNECTED else "orange"


BIG_FRAME_WINDOW = 50   # 最近 50 帧（20Hz ≈ 2.5s），同 lanlinkd 的 MODEL_FRAMES
BIG_FRAME_MIN_SHARE = 0.9   # 45/50


class BigFrameWindow:
  """最近 50 帧 modelV2.big；窗口满且大模型占比 ≥90%（45/50） 才算「大模型在工作」。"""
  def __init__(self):
    self._frames: deque[bool] = deque(maxlen=BIG_FRAME_WINDOW)

  def push(self, big: bool) -> None:
    self._frames.append(bool(big))

  def clear(self) -> None:
    self._frames.clear()

  def mostly_big(self) -> bool:
    return len(self._frames) == BIG_FRAME_WINDOW and sum(self._frames) >= BIG_FRAME_MIN_SHARE * BIG_FRAME_WINDOW


def npu_icon(enabled: bool, mostly_big: bool) -> str:
  """侧边栏 NPU 图标，与行车 HUD 同口径：关 → gray；开 + 大模型在工作 → green；开 + 其余 → orange。"""
  if not enabled:
    return "gray"
  return "green" if mostly_big else "orange"
