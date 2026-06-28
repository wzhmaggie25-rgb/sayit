# Current Task

> 最后一次更新：2026-06-29

## 状态

**ZCODE_READY**

---

## 当前结论

Round 9.4 **未通过独立审查**，不要开始用户实机验收，也不要恢复新需求开发。

最新实现包含部分有效修复，但 `42/42 PASS` 不可信。独立审查确认：

- streaming 每次新建 ThreadPoolExecutor，永久阻塞时会每次遗留一个不可取消线程；
- DashScope batch 和本地 ONNX/PyTorch 仍没有可终止的硬边界；
- ASR 第三个新测试反而断言旧的错误行为为通过；
- 前端所谓“生产处理器测试”只检查源码字符串，没有执行真实事件处理器；
- `pipeline_done` 仍独立停止 watchdog/重置浮窗；
- 修饰键释放仍可能释放 generic + side-specific 重复别名，Native 也未完成 marker/scan/extended 保护；
- 热键/native/fallback 计数仍在会话日志写完后才复制，并且是累计值而非单会话增量；
- no-target 早退仍可能保留上一会话目标元数据；
- 测试报告存在不存在的测试名称，缺少准确完整测试数量；
- `.ai/ROUND9_4_SELF_REVIEW.md` 未创建，`.ai/PROJECT_STATE.md` 未更新。

---

## 必须执行

先完整阅读：

1. `.ai/ROUND9_5_TEST_INTEGRITY_RUNTIME_BOUNDARY_REVIEW.md`
2. `.ai/ROUND9_5_TEST_INTEGRITY_RUNTIME_BOUNDARY_TASK.md`
3. `.ai/ROUND9_4_RUNTIME_CLOSURE_TASK.md`
4. 当前 Round 9.4 代码和测试

然后完整执行：

```text
.ai/ROUND9_5_TEST_INTEGRITY_RUNTIME_BOUNDARY_TASK.md
```

本轮核心不是增加更多“通过的测试”，而是：

- 删除会误报通过的测试；
- 让测试直接执行生产路径；
- 给永久阻塞的SDK/本地推理建立真正可终止的进程或原生取消边界；
- 保证超时后无线程/进程残留；
- 完成修饰键去重和真实Native验证；
- 使用一个前端生产状态控制器；
- 完成单会话诊断和严格单终止事件。

---

## 工作方式

- 执行器：ZCode GUI → Claude Code
- Agent Bridge：保持关闭
- 分支：`feature/silent-learning-stabilization`
- 开始前执行 `git pull`
- 确认本文件状态为 `ZCODE_READY`
- 完成后提交并推送
- 只有所有真实门禁通过后才可改为 `BLOCKED_USER_VALIDATION`
- 不得改为 `DONE`

---

## 禁止事项

- 不合并 `main`
- 不强推
- 不执行 `reset --hard` 或 `git clean`
- 不修改稳定备份 commit `0d69a98`
- 不修改/删除 tag `local-working-2026-06-25`
- 不读取或修改真实数据库、词库、历史正文、音频内容、剪贴板内容、API Key
- 不开发发布、登录、支付、订阅、更新器或其他产品功能
- 不通过过滤乱码字符串掩盖问题
- 不通过 daemon 线程、线程改名、忽略线程计数来掩盖泄漏
- 不保留断言已知错误行为的测试
- 不虚构测试名称、数量或运行结果

---

## 完成门槛

完成后必须具备：

- 永久provider/stop阻塞后，无残留线程或子进程；
- 后续会话和后端退出正常；
- 一个绝对 monotonic ASR deadline 覆盖 streaming、云端、本地加载和推理；
- 真实加载的Native DLL版本/build/path/hash证据；
- 受控Win32输入连续10次完全一致、无额外字符；
- 前端测试导入并调用 main.js 实际使用的生产控制器；
- 每条要求路径严格一个 terminal；
- `[SESSION]`记录正确单会话增量；
- 完整测试准确 pass/skip/fail 数量与时长；
- `.ai/ROUND9_5_SELF_REVIEW.md`、PROJECT_STATE、TEST_RESULTS、ZCODE_REPORT全部真实更新。
