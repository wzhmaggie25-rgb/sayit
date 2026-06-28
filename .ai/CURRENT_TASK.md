# Current Task

> 最后一次更新：2026-06-28

## 状态

**ZCODE_READY**

---

## 当前结论

Round 9.3 暂不接受。

用户实机测试重新出现固定乱码前缀：

```text
FEVHLBIGKOPS
```

这与 `CHANGELOG.md` 记录的 2026-06-13 修饰键释放乱码属于同一故障家族。独立审查还发现 Round 9.3 存在生产路径未闭环：

- `force=True` 仍可绕过修饰键物理状态保护；
- Native `ForceReleaseAlt()` 仍无条件释放多个 Alt VK；
- tri-state 改名后仍有旧的 `editability == "editable"` 判断，导致选择感知 Win32 路径不可达；
- ASR 级联把同一个旧 `remaining` 传给所有引擎，未逐级重算；
- `_STOP_EXECUTOR(max_workers=1)` 可被永久阻塞的 SDK stop 污染；
- 前端测试没有调用 `main.js` 实际使用的完整事件处理路径；
- 热键计数在会话日志写完后才复制，日志仍是默认值。

因此暂停新需求开发，先执行一次完整的 Round 9.4 运行时收口。

---

## 执行任务

必须先阅读：

1. `.ai/ROUND9_4_RUNTIME_CLOSURE_REVIEW.md`
2. `.ai/ROUND9_4_RUNTIME_CLOSURE_TASK.md`
3. `.ai/ROUND9_3_SELF_REVIEW.md`
4. `CHANGELOG.md` 中 `2026-06-13 — 注入乱码修复`

然后完整执行：

```text
.ai/ROUND9_4_RUNTIME_CLOSURE_TASK.md
```

不得只修复 `FEVHLBIGKOPS` 字符串；必须同时完成任务文档中的修饰键源头、tri-state生产路由、全局ASR期限、永久stop阻塞、前端真实处理器、终止事件和会话诊断收口。

---

## 工作方式

- 执行器：ZCode GUI → Claude Code
- Agent Bridge：保持关闭
- 分支：`feature/silent-learning-stabilization`
- 开始前：`git pull`，确认看到本文件状态为 `ZCODE_READY`
- 完成后：提交并推送，状态改为 `BLOCKED_USER_VALIDATION`
- 不得进入 `DONE`

---

## 禁止事项

- 不合并 `main`
- 不强推
- 不执行 `reset --hard` 或 `git clean`
- 不修改稳定备份 commit `0d69a98`
- 不修改/删除 tag `local-working-2026-06-25`
- 不读取或修改真实用户数据库、词库、历史正文、音频内容、剪贴板内容、API Key
- 不开发发布、登录、订阅、支付、更新器或其他新功能
- 不通过过滤 `FEVHLBIGKOPS` / `fevhlbigktcps` 掩盖问题
- 不降低测试断言来制造通过

---

## 完成门槛

只有任务文档所有门禁通过后，才允许改为：

```text
BLOCKED_USER_VALIDATION
```

届时保留一次很短的用户实机检查：记事本连续输入、右Alt开始/停止、无乱码/无菜单激活。通过ChatGPT独立复审后，项目才恢复新需求开发。
