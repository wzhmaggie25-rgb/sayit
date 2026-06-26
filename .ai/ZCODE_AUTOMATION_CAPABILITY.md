# ZCode 自动化能力评估

> 评估日期：2026-06-26 14:54
> 评估方式：只读探查（未安装/升级/修改任何软件）

---

## 1. CLI （命令行界面）

| 项目 | 结果 | 证据 |
|------|------|------|
| `zcode` 在 PATH 上 | ❌ 不存在 | `where zcode`, `which zcode`, `command -v zcode` 均返回 not found / exit 1 |
| `ZCode.exe --help` | ⚠️ 无有用 CLI 输出 | 执行后启动 Electron 窗口，输出仅含 `crash-capture`、`deep-link 注册协议成功`、`electron initialized env=prod version=3.1.7` 等日志，**没有** `--help` 用法文本 |
| `ZCode.exe --version` | ⚠️ 同上 | 同样启动窗口返回版本 3.1.7，无标准 `--version` 输出 |
| ZCode 可执行文件 | `D:\Soft\zcode\ZCode.exe` (212 MB, Electron 应用) | Electron 外壳，无暴露 CLI 子命令 |
| `.zcode/cli/exec/` 目录 | 仅含会话工件 | 5 个 `sess_*` 文件（序列化会话状态），无可执行入口点 |

**结论：ZCode 没有暴露 CLI 接口供外部脚本调用。**

---

## 2. Headless / 非交互模式

| 项目 | 结果 | 证据 |
|------|------|------|
| ZCode.exe 无头模式 | ❌ 不支持 | 每次启动弹出 GUI 窗口；无 `--headless`、`--batch` 等标志 |
| 后台守护进程 | ❌ 未发现 | 无 `zcode service` / `zcode daemon` 概念 |
| Node REPL MCP server | 无关（被 ZCode 消费） | `node_repl` 是 ZCode **消费** 的外部 MCP 服务器，不是 ZCode 自身暴露的接口 |
| Playwright MCP server | 无关（同上） | `playwright` 同样是被 ZCode 消费的外部 MCP |

**结论：ZCode 没有 headless / 非交互模式。**

---

## 3. MCP （Model Context Protocol）能力

| 项目 | 结果 | 证据 |
|------|------|------|
| ZCode 作为 MCP 服务器 | ❌ 否 | ZCode 是 MCP **客户端**，配置文件 (`~/.zcode/cli/config.json`) 仅定义 `servers`（被消费方），无 `server` 或暴露自身为 MCP 服务端 |
| ZCode 支持 MCP 传输层 | ⚠️ 内部使用命名管道 | `node_repl` 使用 `\\.\pipe\codex-computer-use-*` 命名管道，但这是内部实现细节 |
| 外部可连接 ZCode MCP | ❌ 不能 | 无公开端点、无端口监听、无 Unix socket |

**结论：ZCode 不暴露任何 MCP 服务端接口。**

---

## 4. URI Scheme （协议处理器）

| 项目 | 结果 | 证据 |
|------|------|------|
| `zcode://` URI scheme | ✅ 已注册 | `HKEY_CLASSES_ROOT\zcode` 存在，`URL Protocol` 值已设置 |
| zcode:// 处理命令 | 指向 `ZCode.exe "%1"` | `HKEY_CLASSES_ROOT\zcode\shell\open\command` = `"D:\Soft\zcode\ZCode.exe" "%1"` |
| 支持哪些操作 | ❌ 无法确定 | ZCode.exe 收到 `zcode://` URI 后的行为未文档化。启动日志仅显示 `deep-link 注册协议成功`。可能用于打开特定会话/项目，但无公开的 URL 格式规范 |
| `codex://` URI scheme | ✅ 已注册 | `HKEY_CLASSES_ROOT\codex` 存在，但 **无 `shell\open\command`** 子项 |

**结论：`zcode://` URI scheme 已注册但用途不透明，无可用文档说明 URL 格式或支持的操作。**

---

## 5. 外部任务接口总结

| 接口类型 | 可用性 | 备注 |
|----------|--------|------|
| CLI 子命令 | ❌ | 无 |
| Headless 模式 | ❌ | 无 |
| MCP 服务端 | ❌ | 只能是客户端 |
| URI Scheme 远程控制 | ⚠️ | 注册了但无规范文档 |
| HTTP API | ❌ | 无监听端口 |
| IPC / Named pipe | ⚠️ | 内部使用，非公开 API |
| 标准输入管道 | ❌ | 不支持 |

**最终判定：不存在可靠的外部接口可以自动化调用 ZCode。**

---

## 6. 本机可命令行代码代理候选

以下是在 PATH 上发现的、可作为本地脚本调用代码代理的工具：

### 一级候选（可直接用于代码生成/编辑任务）

| 工具 | 路径 | 版本 | 非交互模式 | 备注 |
|------|------|------|-----------|------|
| **Claude Code** | `C:\Users\46136\AppData\Roaming\npm\claude` (npm) + `D:\AI\claude.exe` | 2.1.185 | ✅ `-p/--print` | 功能最完整的代码代理，支持 `-p` pipe 模式、`--output-format json/stream-json`、`--input-format stream-json`，可脚本化调用 |
| **Cursor** | `D:\Soft\cursor\resources\app\bin\cursor` | 3.8.11 | ❌ 编辑器启动器 | 只能打开 IDE 窗口，`-w --wait` 等待文件关闭，无代码生成 CLI |

### 二级候选（通用工具，需自行搭桥）

| 工具 | 路径 | 版本 | 备注 |
|------|------|------|------|
| Python | `C:\Users\46136\AppData\Local\Programs\Python\Python312\python.exe` | 3.12.x | 可编写自定义脚本调用 LLM API |
| Node.js | `D:\Soft\Node\node.exe` | v24.15.0 | 同上 |

### 不可用 / 不存在的工具

| 工具 | 状态 | 备注 |
|------|------|------|
| aider / aider-chat | ❌ 不在 PATH | 未安装 |
| gh / gh-copilot | ❌ 不在 PATH | GitHub CLI 未安装 |
| ollama | ❌ 不在 PATH | 本地 LLM 运行器未安装 |
| gemini | ❌ 不在 PATH | Google Gemini CLI 未安装 |
| continue | ❌ 不在 PATH | Continue.dev CLI 未安装 |
| codex / dcode / oai | ❌ 不在 PATH | Codex CLI 二进制不存在于 PATH；CODEX_CLI_PATH 指向的路径 (`C:\Users\46136\AppData\Local\OpenAI\Codex\bin\330bd0cba6496126\codex.exe`) 文件也已不存在 |

### 推荐

若需要从 SayIt 项目内脚本化调用代码代理，**Claude Code（`claude -p`）是唯一现成可用的非交互代码代理**。示例：
```bash
claude -p "Explain the bug in file X" --output-format json
```

---

## 7. 附录：探查命令清单

```bash
# PATH 检查
where zcode                    → not found
where codex                    → not found
where claude                   → found (2 locations)
where aider                    → not found
where gemini                   → not found
where cursor                   → found
where gh                       → not found
where ollama                   → not found
where continue                 → not found

# ZCode 可执行文件检查
D:/Soft/zcode/ZCode.exe --help     → 仅日志，无 CLI 用法
D:/Soft/zcode/ZCode.exe --version  → 版本 3.1.7

# 注册表检查
reg query HKCR\zcode               → scheme 已注册
reg query HKCR\zcode\shell\open\command → "D:\Soft\zcode\ZCode.exe" "%1"
reg query HKCR\codex               → scheme 已注册（无 open command）

# ZCode 配置检查
~/.zcode/cli/config.json           → MCP servers（客户端角色）
~/.zcode/v2/config.json            → API 密钥（未输出内容）