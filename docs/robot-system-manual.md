# 语音机器人系统说明书

本文说明 Agent 服务端、树莓派运行端、烧录装机、OTA、日常使用和维护方法。当前生产调试入口为 `http://103.236.93.62:32020/login`，测试访问时默认不走代理。

## 1. 系统边界

系统分为两端：

- Agent 服务端：运行在 `prod-web-02`，负责 Web 管理端、Agent Harness、Hermes/Memory/认知层、机器人设备鉴权、OTA manifest、WebSocket 语音消息入口。
- 树莓派运行端：代码位于 `cube-robot-runtime/`，只负责设备身份、网络连接、音频采集/播放、OTA 执行和本地服务守护。树莓派不是大脑，不直接包含 cognition、Hermes 或 Agent 服务端代码。

两端只通过 Robot Protocol v1 通信：

- HTTP OTA：`/api/v1/robot/ota/manifest/{device_id}`
- WebSocket 语音链路：`/api/v1/robot/ws/{device_id}`
- Web 调试入口：`/login`

当前状态：

- Agent 服务端已部署并能通过无硬件 probe 验证 OTA、login 和 WebSocket。
- Pi 端 runtime、systemd unit、首次启动脚本、OTA dry-run 脚本已具备。
- 真正的麦克风采集、TTS/扬声器播放、自动下载并切换 OTA release 还需要后续实现和实机验证。

## 2. Agent 服务端安装与部署

### 2.1 首次安装

在新 Linux 服务器上进入仓库目录，执行：

```bash
sudo bash install.sh --mode auto --yes
```

如果服务器访问官方源不稳定：

```bash
sudo env AGENT_HUB_MIRROR_MODE=auto bash install.sh --mode auto --yes
```

安装器会保留已有的 `/etc/agent-hub/secrets.env` 和 `/var/lib/agent-hub`，重复运行会进入修复/升级路径，不会覆盖已有密钥和数据。

### 2.2 生产运行目录

生产环境当前采用 release 目录切换：

- 当前运行入口：`/opt/agent-hub/current`
- 历史 release：`/opt/agent-hub/releases/`
- 数据目录：`/var/lib/agent-hub`
- 密钥配置：`/etc/agent-hub/secrets.env`
- Web/API 入口由 Caddy 对外暴露，API 本身监听本机端口。

部署新版本时，先打包当前 Git 提交，上传到服务器，展开到新的 `/opt/agent-hub/releases/<timestamp>-<sha>-<name>`，复用已有 `.venv`，切换 `/opt/agent-hub/current`，再重启：

```bash
sudo systemctl restart agent-hub-api agent-hub-worker
sudo systemctl reload caddy
```

部署后按规则清理旧 release，只保留最近可回滚的几个版本。不要删除：

- `/etc/agent-hub/secrets.env`
- `/var/lib/agent-hub`
- 当前 `/opt/agent-hub/current` 指向的 release
- 数据库、上传文件、日志中仍需留存的审计资料

### 2.3 服务状态和日志

常用命令：

```bash
scripts/agent-hub status
scripts/agent-hub logs
scripts/agent-hub doctor
scripts/agent-hub backup /tmp/agent-hub-backup.tar.gz
scripts/agent-hub backup verify /tmp/agent-hub-backup.tar.gz
```

生产服务器也可以直接看 systemd：

```bash
systemctl status agent-hub-api agent-hub-worker agent-hub-litellm caddy --no-pager
journalctl -u agent-hub-api -n 200 --no-pager
journalctl -u agent-hub-worker -n 200 --no-pager
journalctl -u caddy -n 100 --no-pager
```

健康检查：

```bash
curl -fsS http://127.0.0.1:8000/health/live
curl -fsS http://127.0.0.1:8000/health/ready
curl --noproxy '*' -I http://103.236.93.62:32020/login
```

### 2.4 机器人设备 token

机器人设备 token 放在服务器 `/etc/agent-hub/secrets.env`，不要提交到 Git、截图或聊天记录。

格式示例：

```bash
AGENT_HUB_ROBOT_DEVICE_TOKENS=pi-lab-01:replace-with-secret-token
```

修改后重启 API：

```bash
sudo systemctl restart agent-hub-api
```

验证 token 绑定时使用无硬件 probe，不要把真实 token 打印到日志里。

## 3. 无硬件联调

没有树莓派时，使用 `tools/robot_voice_probe.py` 验证服务端机器人链路。

在本地或服务器仓库目录执行：

```bash
python tools/robot_voice_probe.py \
  --base-url http://103.236.93.62:32020 \
  --device-id pi-lab-01 \
  --device-token '<server-configured token>' \
  --utterance '你好'
```

该 probe 会检查：

- OTA manifest 是否返回 200。
- `/api/v1/auth/login` 路由是否可达。
- WebSocket 是否能发送 heartbeat 和最终语音文本。
- 服务端是否返回 `assistant.text.done`。

正常结果中应看到：

```json
{
  "ota_manifest": {"ok": true},
  "login": {"ok": true},
  "websocket": {"ok": true, "received_type": "assistant.text.done"}
}
```

如果 WebSocket probe 提示缺少 `websocket-client`，只在测试环境安装：

```bash
python -m pip install websocket-client
```

## 4. 树莓派烧录与首次启动

### 4.1 准备镜像

建议使用 Raspberry Pi OS Lite 64-bit。烧录时在 Raspberry Pi Imager 或等效工具中预配置：

- 主机名，例如 `cube-robot-pi-01`
- SSH 开启
- 一个非默认登录用户
- Wi-Fi SSID/密码，或准备有线网络
- 时区：中国环境可设为 `Asia/Shanghai`

烧录后把 SD 卡插入树莓派，接电启动。第一次启动后，先确认网络和时间：

```bash
hostname -I
timedatectl
ping -c 3 103.236.93.62
```

### 4.2 安装系统依赖

进入树莓派：

```bash
ssh <pi-user>@<pi-ip>
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl tar
```

音频实机阶段还需要按硬件选择安装录音/播放工具，例如 ALSA：

```bash
sudo apt install -y alsa-utils
```

### 4.3 安装 Pi runtime

把仓库中的 `cube-robot-runtime/` 打包复制到树莓派，例如：

```bash
tar -czf cube-robot-runtime.tar.gz cube-robot-runtime
scp cube-robot-runtime.tar.gz <pi-user>@<pi-ip>:/tmp/
```

在树莓派上安装到固定目录：

```bash
sudo mkdir -p /usr/local/lib/cube-robot
sudo tar -xzf /tmp/cube-robot-runtime.tar.gz -C /usr/local/lib/cube-robot --strip-components=1
cd /usr/local/lib/cube-robot
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

首次启动前先 dry-run：

```bash
sudo /usr/local/lib/cube-robot/scripts/first-boot-register.sh --dry-run
```

确认输出路径是：

- 配置目录：`/etc/cube-robot`
- 状态目录：`/var/lib/cube-robot`
- 设备身份：`/etc/cube-robot/device-id`

确认无误后执行正式注册：

```bash
sudo /usr/local/lib/cube-robot/scripts/first-boot-register.sh
```

### 4.4 写入机器人配置

编辑 `/etc/cube-robot/robot.toml`：

```toml
[runtime]
device_id = "pi-lab-01"
server_url = "ws://103.236.93.62:32020/api/v1/robot/ws/pi-lab-01"
device_token = "replace-with-server-configured-token"
language = "zh"
voice_id = "replace-with-minimax-voice-id"
tts_model = "speech-2.8-turbo"

[audio]
codec = "wav"
sample_rate_hz = 16000
channels = 1
duration_seconds = 4.0
# 如果有多个麦克风，先用 arecord -l 找到设备，再打开这一行。
# device = "plughw:1,0"

[listen]
probe_duration_seconds = 0.75
voice_threshold = 0.02
idle_sleep_seconds = 0.2
cooldown_seconds = 0.75
session_id_prefix = "listen"

[updates]
channel = "stable"
manifest_url = "http://103.236.93.62:32020/api/v1/robot/ota/manifest/pi-lab-01"
check_interval_minutes = 30
```

权限建议：

```bash
sudo chown cube-robot:cube-robot /etc/cube-robot/robot.toml
sudo chmod 0640 /etc/cube-robot/robot.toml
```

## 5. 树莓派运行与使用

### 5.1 手动 dry-run

先不用 systemd，直接跑一次文本语音链路：

```bash
cd /usr/local/lib/cube-robot
.venv/bin/cube-robot dry-run \
  --server-url ws://103.236.93.62:32020/api/v1/robot/ws/pi-lab-01 \
  --device-id pi-lab-01 \
  --device-token '<server-configured token>' \
  --utterance '你好'
```

如果成功，应返回已发送的消息类型和收到的 assistant 文本。

### 5.2 手动 voice-once

`voice-once` 会在树莓派本地录一段音频，发送到服务端做 ASR 和 Agent 处理，再播放服务端返回的 TTS 音频。树莓派不保存 MiniMax API key。

先确认本机有录音和播放命令：

```bash
arecord -l
aplay -l
which mpg123 || which mpg321 || which mpv
```

如果没有 MP3 播放器，安装一个：

```bash
sudo apt-get update
sudo apt-get install -y mpg123
```

执行一轮真实语音交互：

```bash
cd /usr/local/lib/cube-robot
.venv/bin/cube-robot voice-once --config /etc/cube-robot/robot.toml --session-id voice-session-1
```

成功时输出里应包含：

- `sent_types` 包含 `audio.start`、`audio.chunk`、`audio.end`
- `received_types` 包含 `speech.partial`、`assistant.text.done`、`tts.audio.chunk`、`tts.audio.done`
- `played_audio_codecs` 包含 `mp3`

### 5.3 手动 listen

`listen` 是树莓派常驻交互入口。它先录短探测片段，用本地 RMS 能量阈值判断是否有人声；达到阈值后触发一次完整 `voice-once`，再进入冷却，避免把机器人自己的播放声再次当成用户输入。

```bash
cd /usr/local/lib/cube-robot
.venv/bin/cube-robot listen --config /etc/cube-robot/robot.toml --max-turns 1
```

调试时可按环境调整：

```bash
.venv/bin/cube-robot listen \
  --config /etc/cube-robot/robot.toml \
  --probe-duration-seconds 0.75 \
  --voice-threshold 0.02 \
  --cooldown-seconds 0.75
```

如果环境噪声较大，提高 `voice_threshold`；如果很难触发，降低 `voice_threshold`。`[audio].duration_seconds` 是正式对话录音长度，`[listen].probe_duration_seconds` 只是判断是否开始录音的探测长度。

### 5.4 安装 systemd 服务

当前 service 通过 `bash /var/lib/cube-robot/current/scripts/run-runtime.sh` 启动，避免 Windows 打包时脚本可执行位丢失导致 systemd 启动失败。首次安装时可以把当前源码目录链到 runtime current；启动脚本会优先复用 `/usr/local/lib/cube-robot/.venv` 中已安装的依赖，并把当前 release 源码加入 `PYTHONPATH`：

```bash
sudo mkdir -p /var/lib/cube-robot/releases
sudo ln -sfn /usr/local/lib/cube-robot /var/lib/cube-robot/current
sudo cp /usr/local/lib/cube-robot/scripts/cube-robot.service /etc/systemd/system/
sudo cp /usr/local/lib/cube-robot/scripts/cube-robot-updater.service /etc/systemd/system/
sudo cp /usr/local/lib/cube-robot/scripts/cube-robot-updater.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cube-robot.service
sudo systemctl start cube-robot.service
```

查看运行状态：

```bash
systemctl status cube-robot.service --no-pager
journalctl -u cube-robot.service -n 100 --no-pager
```

### 5.5 日常使用

正常使用时流程是：

1. 树莓派启动 `cube-robot.service`。
2. Runtime 进入 `listen` 循环，在本地录制短探测片段。
3. 探测片段达到本地人声阈值后，Runtime 触发一次完整 `voice-once`。
4. `voice-once` 建立到 Agent 服务端的 WebSocket，发送 heartbeat 和音频事件。
5. 服务端完成 ASR、Agent/Hermes/Memory/认知层处理和 TTS。
6. Pi 端播放服务端返回的 TTS 音频，并在冷却后回到监听。

当前代码已经打通文本 dry-run、音频上传、服务端 ASR/TTS provider、`voice-once` 播放和本地 `listen` 自动触发。唤醒词、打断交互和更低延迟流式播放仍属于后续增强。

## 6. OTA 使用

### 6.1 当前 OTA 能力

当前 OTA 是规划和校验阶段，默认 updater service 执行 `--dry-run`，不会真正下载、安装或切换 release。

可验证内容：

- Agent 服务端能返回 OTA manifest。
- Pi 端能读取配置并规划 staged release 目录。
- `ota-update.sh --dry-run` 不会修改 `/var/lib/cube-robot/current`。

### 6.2 手动 OTA dry-run

在树莓派上执行：

```bash
sudo /usr/local/lib/cube-robot/scripts/ota-update.sh \
  --dry-run \
  --config /etc/cube-robot/robot.toml
```

预期输出类似：

```text
dry-run: would inspect /etc/cube-robot/robot.toml
dry-run: would stage releases under /var/lib/cube-robot/releases
dry-run: would update /var/lib/cube-robot/current after verification
```

### 6.3 定时 OTA dry-run

开启 updater timer：

```bash
sudo systemctl enable cube-robot-updater.timer
sudo systemctl start cube-robot-updater.timer
systemctl list-timers cube-robot-updater.timer --no-pager
```

查看 OTA 日志：

```bash
journalctl -u cube-robot-updater.service -n 100 --no-pager
```

### 6.4 后续真正 OTA 需要补齐

真正 OTA 上线前，需要补齐并验证：

- manifest 指向真实 runtime artifact。
- 下载 artifact。
- 校验 sha256。
- 校验签名。
- 解压到 `/var/lib/cube-robot/releases/<version>`。
- 切换 `/var/lib/cube-robot/current`。
- 重启 `cube-robot.service`。
- 健康检查失败时自动回滚到上一个 release。
- Web 管理端展示设备版本、OTA 状态和失败原因。

## 7. Agent 端维护

### 7.1 MiniMax 语音配置

MiniMax API key 只放服务器，不放树莓派、不提交 Git、不写入聊天或日志。编辑服务器 `/etc/agent-hub/secrets.env`：

```bash
sudo nano /etc/agent-hub/secrets.env
```

加入或更新：

```bash
MINIMAX_API_KEY=<your-minimax-api-key>
AGENT_HUB_ROBOT_VOICE_MEDIA_PROVIDER=minimax
AGENT_HUB_MINIMAX_TTS_VOICE_ID=<system-or-cloned-voice-id>
AGENT_HUB_MINIMAX_TTS_MODEL=speech-2.8-turbo
AGENT_HUB_MINIMAX_TTS_AUDIO_FORMAT=mp3
AGENT_HUB_MINIMAX_TTS_SAMPLE_RATE_HZ=32000
```

改完重启服务：

```bash
sudo systemctl restart agent-hub-api
sudo systemctl status agent-hub-api --no-pager
```

如果还没有克隆音色，先用 MiniMax 官方系统音色 ID。克隆完成后，把克隆得到的 `voice_id` 写入 `AGENT_HUB_MINIMAX_TTS_VOICE_ID`，或者写入树莓派 `/etc/cube-robot/robot.toml` 的 `voice_id`。

### 7.2 每日检查

```bash
systemctl is-active agent-hub-api agent-hub-worker agent-hub-litellm caddy
curl -fsS http://127.0.0.1:8000/health/ready
curl --noproxy '*' -I http://103.236.93.62:32020/login
```

机器人链路检查：

```bash
python tools/robot_voice_probe.py \
  --base-url http://103.236.93.62:32020 \
  --device-id pi-lab-01 \
  --device-token '<server-configured token>' \
  --utterance '日常巡检'
```

### 7.3 备份

升级、改配置、做大迁移前先备份：

```bash
scripts/agent-hub backup /tmp/agent-hub-backup.tar.gz
scripts/agent-hub backup verify /tmp/agent-hub-backup.tar.gz
```

重点保护：

- `/var/lib/agent-hub`
- 数据库
- `/etc/agent-hub/secrets.env`
- Caddy/TLS 配置
- 模型供应商密钥

### 7.4 模型、Hermes 和认知层维护

机器人体验主要由服务端大脑决定，Pi 端只做输入输出。维护重点：

- 模型配置：检查模型池、额度、失败率和 fallback。
- Hermes/Memory：保留高价值长期记忆，避免把所有聊天流水塞进上下文。
- 认知层：记录经验、反思、belief、relationship、world state、skill 的版本和置信度。
- 失败记录：认知层失败、错误决策、用户纠正和糟糕回复要进入经验/反思记录，后续检索时避免重复犯错。
- 权限边界：普通 reflection 不能自动修改核心 SOUL、人格、安全规则和工具权限。

### 7.5 清理策略

可以定期清理：

- `/tmp` 中旧部署包。
- 超出保留数的 `/opt/agent-hub/releases/*`。
- 本地 `.pytest_cache`、`.ruff_cache`、`__pycache__`。
- 过期日志归档。

不要自动清理：

- `/var/lib/agent-hub`
- `/etc/agent-hub/secrets.env`
- 数据库文件或备份
- 当前 release
- 未确认已归档的重要认知/记忆数据

## 8. 树莓派端维护

### 8.1 每日检查

```bash
systemctl is-active cube-robot.service
journalctl -u cube-robot.service -n 100 --no-pager
```

网络：

```bash
ping -c 3 103.236.93.62
curl -I http://103.236.93.62:32020/login
```

音频：

```bash
arecord -l
aplay -l
speaker-test -t wav -c 2
```

### 8.2 重启

```bash
sudo systemctl restart cube-robot.service
```

如果配置变化：

```bash
sudo systemctl daemon-reload
sudo systemctl restart cube-robot.service
```

### 8.3 回滚

记录当前版本：

```bash
readlink -f /var/lib/cube-robot/current
```

如果 OTA 或手动 release 切换后失败，停止服务并恢复旧 current：

```bash
sudo systemctl stop cube-robot.service
sudo ln -sfn /var/lib/cube-robot/releases/<previous-version> /var/lib/cube-robot/current
sudo systemctl start cube-robot.service
```

回滚后再看日志：

```bash
journalctl -u cube-robot.service -n 200 --no-pager
```

## 9. 常见故障

### 9.1 login 页面打不开

检查：

```bash
curl --noproxy '*' -I http://103.236.93.62:32020/login
systemctl status caddy --no-pager
journalctl -u caddy -n 100 --no-pager
```

如果服务器本机 health 正常但公网打不开，优先查防火墙、安全组、Caddy 和端口映射。

### 9.2 WebSocket 连接失败

检查：

- `device_id` 是否和 URL 中一致。
- `X-Robot-Device-Token` 或配置里的 `device_token` 是否匹配服务器。
- URL 是否使用 `ws://103.236.93.62:32020/api/v1/robot/ws/pi-lab-01`。
- 是否被代理拦截；生产调试默认不走代理。

### 9.3 OTA 返回 401

说明设备 token 错误或服务器未配置该设备：

```bash
sudo grep AGENT_HUB_ROBOT_DEVICE_TOKENS /etc/agent-hub/secrets.env
sudo systemctl restart agent-hub-api
```

不要把 token 值复制到工单、聊天或日志。

### 9.4 OTA 返回 422

通常是请求参数不合法，例如 `current_version` 格式错误。probe 默认使用 `2026.09.10+0`，不要改成随意字符串。

### 9.5 Agent 有回复但机器人不播放

分层排查：

1. 服务端 probe 是否收到 `assistant.text.done`。
2. Pi WebSocket 是否收到服务端消息。
3. Pi 播放模块是否被调用。
4. 本地扬声器 `speaker-test` 是否正常。
5. TTS 或音频格式是否和播放设备兼容。

### 9.6 Agent 变得混乱或记忆错误

不要直接增加更多上下文。优先：

- 查看最近的 Hermes/认知层写入。
- 降低错误 belief 或经验的 confidence。
- 标记 contradiction 和 last_verified。
- 把失败案例写入 Reflection/Experience，作为后续策略约束。
- 核心 SOUL、人格、安全规则不要由普通 reflection 自动修改。

## 10. 周六实机验收清单

拿到树莓派后，按顺序验收：

1. SD 卡烧录并能 SSH 登录。
2. Pi 能访问 `103.236.93.62:32020`。
3. `/etc/cube-robot/robot.toml` 写入正确 device id、WS URL 和 token。
4. `first-boot-register.sh --dry-run` 输出路径正确。
5. `first-boot-register.sh` 正式创建用户、配置目录和状态目录。
6. `cube-robot dry-run` 能收到 `assistant.text.done`。
7. `ota-update.sh --dry-run` 能规划 release，不修改 current。
8. `cube-robot.service` 能启动并持续运行。
9. 麦克风录音和扬声器播放分别验证通过。
10. 一句真实语音完成“用户说话 -> 服务端 Agent -> 树莓派播放”闭环。
11. 日志中不出现 token、模型密钥或用户敏感信息。
12. 断网重连、重启恢复、服务异常重启至少各测一次。

## 11. 安全规则

- token 和模型密钥只放在服务器或 Pi 本机配置文件中。
- 不把真实 token 写入 Git、截图、聊天记录、日志样例。
- Pi 端不要引入 Agent 服务端源码，也不要直接访问 Hermes/Memory 数据库。
- Agent 端可以学习经验和技能，但不能让普通 reflection 自动修改核心人格、安全策略和工具权限。
- OTA 正式上线前必须具备 checksum、签名、健康检查和回滚。
