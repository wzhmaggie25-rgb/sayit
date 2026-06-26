# Current Task
> 最后一次更新：2026-06-26 14:00

## 任务描述

只读审计当前静默学习功能，确认最早失败断点，不修改业务代码。

## 涉及文件

- [ ] `infrastructure/silent_monitor.py` — 核心静默学习逻辑
- [ ] `application/pipeline.py` — 调用 silent_monitor.start() 的 Phase 6
- [ ] `infrastructure/focus_context.py` — UIA 上下文获取
- [ ] `infrastructure/context_helper_dll.py` — 进程内 UIA DLL 加载
- [ ] `infrastructure/context_helper_client.py` — 遗留 subprocess UIA
- [ ] `infrastructure/keyboard_helper_dll.py` — 热键 DLL 加载（审计调用链用）
- [ ] `application/orchestrator.py` — 编排器、pipeline 互斥、SilentMonitor wiring
- [ ] `tests/test_silent_monitor.py` — 已有静默学习测试
- [ ] `tests/smoke_notepad_silent_monitor.py` — 冒烟测试
- [ ] `tests/test_history_and_terminal_learning.py` — 终端学习测试

## 完成条件

- [ ] 绘制真实调用链（已写入 PROJECT_STATE.md）
- [ ] 检查 context helper 实际加载方式（已确认：双路径 — ContextHelperDll + ContextHelperClient）
- [ ] 检查静默学习触发条件（已确认：Phase 6 中 silent_learning config + ok + hwnd）
- [ ] 运行已有相关测试
- [ ] 明确最早失败断点
- [ ] 输出最小修复建议
- [ ] 不修改热键、录音、注入和进程管理

## 备注

- 当前 PROJECT_STATE.md 已有完整调用链描述
- 下一 session 需运行测试并定位断点
- 禁止修改任何业务代码