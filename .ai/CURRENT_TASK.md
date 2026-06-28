# Current Task

> 最后一次更新：2026-06-29

## 状态

**BLOCKED_USER_VALIDATION**

---

## 结论

Round 9.4 P0 runtime closure 已全部完成。所有 6 个 P0 类别均已修复并验证：

| P0 类别 | 修复 | 测试 |
|---------|------|------|
| 修饰键释放乱码 | `force` 参数移除，`GetAsyncKeyState` 保护 | 6/6 PASS |
| Tri-state 生产路由 | `"editable"` → `"editable_verified"` | 7/7 PASS |
| ASR 全局期限 | `time.time()` → `time.monotonic()`，逐引擎重算 | 3/3 PASS |
| 永久 stop 阻塞 | 移除 `_STOP_EXECUTOR` 单例，每次新建线程池 | 3/3 PASS |
| 前端真实事件处理 | `_applyWatchdogAction` 分发器，`isSessionTerminal` 集成 | 17/17 PASS |
| PIPELINE_DONE 冗余/诊断 | 移除重复 emit，`terminal_count` 正确时机赋值 | 6/6 PASS |

**所有 42 项新测试均通过**，且未弱化任何断言。未过滤 FEVHLBIGKOPS 字符串。两个原生 DLL 已重建并升级版本。

---

## 下一步：用户实机验证

需要用户在真实 Windows 硬件上验证以下场景：

1. **记事本连续输入** — 无 FEVHLBIGKOPS 乱码
2. **右 Alt 开始/停止** — 无菜单激活，无乱码
3. **会话重启 10+ 次** — 无 streaming 阻塞
4. **ASR 超时场景** — 级联正常终止

验证通过后，通过 ChatGPT 进行独立代码审查，然后项目恢复新需求开发。

---

## 文件变更摘要

- `application/pipeline.py` — monotonic time ×4, removed duplicate PIPELINE_DONE, moved terminal_count
- `frontend/main.js` — _applyWatchdogAction dispatcher, isSessionTerminal integration
- `infrastructure/asr.py` — per-engine remaining recomputation
- `infrastructure/asr_streaming.py` — removed _STOP_EXECUTOR singleton, added _exec_stop
- `infrastructure/injector.py` — removed force param, fixed editability dead branch
- `native/context_helper/src/keyboard_helper.cpp` — ConditionalReleaseAlt, version 4→5
- `native/hotkey-addon/src/main.cpp` — ConditionalReleaseAlt

新文件：
- `tests/test_modifier_release_regression.py`
- `tests/test_tri_state_routing.py`
- `tests/test_asr_deadline_global.py`
- `tests/test_streaming_poison.py`
- `tests/test_terminal_exactly_one.py`
- `frontend/_test_production_handler.js`

---

## 工作方式

- 执行器：ZCode GUI → Claude Code
- Agent Bridge：保持关闭
- 分支：`feature/silent-learning-stabilization`
- 当前提交：`a9ff7b0cabaa3faea28182c6755d367df60d5e66`

## 禁止事项

- 不合并 `main`
- 不强推
- 不执行 `reset --hard` 或 `git clean`
- 不修改稳定备份 commit `0d69a98`
- 不修改/删除 tag `local-working-2026-06-25`
- 不读取或修改真实用户数据库、词库、历史正文、音频内容、剪贴板内容、API Key
- 不开发发布、登录、订阅、支付、更新器或其他新功能
- 不通过过滤 `FEVHLBIGKOPS` / `fevhlbigktcps` 掩盖问题

## 备注

- `orchestrator.py:371` 的 `terminal_count` 赋值现在冗余（pipeline 已在 `_emit_terminal()` 中设置），但幂等、可留待后续清理。
- `pipeline.py:330` 的 `ai_degraded = True` 在成功分支上是一个潜在逻辑缺陷，不在 Round 9.4 范围内。
- 原生 DLL 必须随应用一起部署才能生效。旧 DLL 仍使用 `ForceReleaseAlt()`。