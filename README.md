# Sayit

Windows 桌面语音输入工具。按下热键即说即转，AI 智能后处理与自学习纠错。

## 功能

- **全局热键录音**：按下右 Alt 开始录音，松开自动转文字
- **三级 ASR 引擎**：阿里云 DashScope → 火山方舟 → ONNX 本地离线
- **AI 智能润色**：通义千问 / 豆包 / DeepSeek / OpenAI 多引擎纠错
- **静默自学习**：注入文本后监控用户手动编辑，自动提取纠错规则
- **个人词库**：三层热词注入（ASR上下文 → 模糊修正 → LLM保留）
- **应用适配**：30+ 应用注入策略（终端/浏览器/Office/IDE/IM）
- **悬浮窗**：录音时显示 RMS 驱动的波形动画

## 快速开始

### 系统要求

- **Windows 10/11**（x64）
- **Python 3.10+**
- **Node.js 18+**

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

> `requirements.txt` 不含 FastAPI / uvicorn，需额外安装：
> ```bash
> pip install fastapi uvicorn
> ```

### 2. 安装 Electron 前端依赖

```bash
cd frontend
npm install
```

### 3. 配置 API 密钥

Sayit 依赖 AI/ASR 云服务，你需要至少一个 API 密钥。

**方式 A — 环境变量（推荐，更安全）：**

```bash
# PowerShell
$env:SAYIT_ALIYUN_API_KEY = "sk-xxxx"

# 或 CMD
set SAYIT_ALIYUN_API_KEY=sk-xxxx
```

支持的环境变量（参见 `.env.example`）：

| 变量 | 用途 |
|---|---|
| `SAYIT_ALIYUN_API_KEY` | 阿里云 DashScope（语音识别 + AI 纠正） |
| `SAYIT_VOLCENGINE_ASR_ACCESS_TOKEN` | 火山引擎 / 豆包（语音识别） |
| `SAYIT_VOLCENGINE_ASR_APP_ID` | 火山引擎 App ID |
| `SAYIT_VOLCENGINE_AI_API_KEY` | 火山引擎 / 豆包（AI 纠正） |
| `SAYIT_DEEPSEEK_API_KEY` | DeepSeek（AI 纠正） |

**方式 B — 配置文件：**

复制配置文件模板并填入密钥：

```bash
cp config.example.json config.json
# 编辑 config.json，填入你的 api_key
```

> 优先级：**环境变量 > config.json > 内置默认值**

### 4. 运行

**方式 A — 双击启动（推荐）：**

```
双击 start.bat
```

或右键点击 `launch_sayit.bat` 发送到桌面快捷方式。

**方式 B — 手动启动（开发调试）：**

```bash
# 终端 1：启动 Python 后端
python server.py

# 终端 2：启动 Electron 前端
cd frontend
set SAYIT_SKIP_BACKEND=1
npx electron .
```

> `SAYIT_SKIP_BACKEND=1` 表示 Electron 不自动启动 Python 后端（已手动启动）。
>
> 不加此环境变量，Electron 会自动启动后端：

```bash
cd frontend
npx electron .    # 会自动 spawn python ../server.py
```

### 使用

按下 **右 Alt** 键开始录音，松开后自动转写为文字并注入到当前光标所在位置。

## 配置

编辑 `%APPDATA%/Sayit/config.json` 或项目根目录的 `config.json` 配置 API 密钥和偏好设置。支持热加载（保存后自动生效）。

## 数据存储

所有用户数据位于 `%APPDATA%/Sayit/`：

- `sayit.db` — SQLite 数据库（历史记录 + 热词库 + 纠错规则）
- `config.json` — 用户配置
- `sayit.log` — 运行日志

## 技术栈

- **UI**: Electron (Chromium)
- **后端**: Python FastAPI
- **音频**: PyAudio 16kHz
- **热键**: WH_KEYBOARD_LL 全局钩子（pynput）
- **ASR**: DashScope / 火山引擎 / ONNX SenseVoice
- **AI**: OpenAI 兼容协议（多 Provider）
- **注入**: UIA ValuePattern / SendInput / Clipboard
- **存储**: SQLite

## 打包

### Python 后端打包为独立 exe

```bash
pip install pyinstaller
pyinstaller sayit-backend.spec
```

### Electron 前端打包

```bash
cd frontend
npm run build    # 生成 release/Sayit-win32-x64/
```

## 版本

v1.10.0