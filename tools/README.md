# openpilot tools

## System Requirements

openpilot is developed and tested on **Ubuntu 24.04**, which is the primary development target aside from the [supported embedded hardware](https://github.com/commaai/openpilot#running-on-a-dedicated-device-in-a-car).

Most of openpilot should work natively on macOS. On Windows you can use WSL for a nearly native Ubuntu experience. Running natively on any other system is not currently recommended and will likely require modifications.

## Native setup on Ubuntu 24.04 and macOS

Follow these instructions for a fully managed setup experience. If you'd like to manage the dependencies yourself, just read the setup scripts in this directory.

**1. Clone openpilot**
``` bash
git clone https://github.com/commaai/openpilot.git
```

**2. Run the setup script**
``` bash
cd openpilot
tools/op.sh setup
```

**3. Activate a Python shell**
Activate a shell with the Python dependencies installed:
``` bash
source .venv/bin/activate
```

**4. Build openpilot**
``` bash
scons -u
```

## WSL on Windows

[Windows Subsystem for Linux (WSL)](https://docs.microsoft.com/en-us/windows/wsl/about) should provide a similar experience to native Ubuntu. [WSL 2](https://docs.microsoft.com/en-us/windows/wsl/compare-versions) specifically has been reported by several users to be a seamless experience.

Follow [these instructions](https://docs.microsoft.com/en-us/windows/wsl/install) to setup the WSL and install the `Ubuntu-24.04` distribution. Once your Ubuntu WSL environment is setup, follow the Linux setup instructions to finish setting up your environment. See [these instructions](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps) for running GUI apps.

**NOTE**: If you are running WSL 2 and experiencing performance issues with the UI or simulator, you may need to explicitly enable hardware acceleration by setting `GALLIUM_DRIVER=d3d12` before commands. Add `export GALLIUM_DRIVER=d3d12` to your `~/.bashrc` file to make it automatic for future sessions.

## CTF
Learn about the openpilot ecosystem and tools by playing our [CTF](/tools/CTF.md).

## Directory Structure

```
├── car_porting/        # Tools for porting new cars
├── release/            # Scripts for building openpilot releases
└── scripts/            # Miscellaneous scripts
```

Development tools such as cabana, plotjuggler, and replay live in [openpilot/tools/](/openpilot/tools/):

```
├── cabana/             # View and plot CAN messages from drives or in realtime
├── camerastream/       # Cameras stream over the network
├── joystick/           # Control your car with a joystick
├── lib/                # Libraries to support the tools and reading openpilot logs
├── plotjuggler/        # A tool to plot openpilot logs
├── replay/             # Replay drives and mock openpilot services
└── sim/                # Run openpilot in a simulator
```

## C3XL 发布

源码仓库为 `https://github.com/lochuan/toyopilot-c3.git`，默认源码分支为 `c3xl-lean`。Mac 上的 `origin` 指向该源码仓库，`gitcode` 指向 `git@gitcode.com:lochuan/toyopilot-c3.git`。

在仓库根目录运行 `tools/release/publish_release_from_device.sh`。脚本先校验本地源码与 `origin` 一致，再由设备上的 `device_release.sh` 从 GitHub 拉取源码并构建扁平发布树。Mac 取回产物后只推送到 GitCode 的 `c3-release`，随后将设备运行树的 `origin` 改为 `https://gitcode.com/lochuan/toyopilot-c3.git`。设备拉取发布分支并校验 SHA 后切换、重启。

`SRC_BRANCH` 和 `RELEASE_BRANCH` 可覆盖默认分支；自定义发布分支也只推送到 `gitcode`。`device_release.sh` 的 `REPO_URL` 仅指定构建源码仓库，不改变发布目标。`c3-release` 按正式发布分支分类。

安装入口为 `tp.diaperastiko.top/c3x`，安装和后续更新均使用 GitCode。旧发布分支停止更新；已安装设备需通过该入口重装，不自动迁移。

