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

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行

```bash
python main.py
```

### 打包

```bash
pip install pyinstaller
pyinstaller sayit.spec
```

## 配置

编辑 `config.json` 配置 API 密钥和偏好设置。支持热加载（保存后 2 秒内自动生效）。

## 数据存储

所有用户数据位于 `%APPDATA%/Sayit/`：
- `sayit.db` — SQLite 数据库（历史记录 + 热词库 + 纠错规则）
- `config.json` — 用户配置
- `sayit.log` — 运行日志

## 技术栈

- **UI**: HTML/CSS/JS via pywebview (Edge WebView2)
- **后端**: Python
- **音频**: PyAudio 16kHz
- **热键**: WH_KEYBOARD_LL 全局钩子
- **ASR**: DashScope / 火山引擎 / ONNX SenseVoice
- **AI**: OpenAI 兼容协议（多 Provider）
- **注入**: UIA ValuePattern / SendInput / Clipboard
- **存储**: SQLite

## 版本

v1.10.0
