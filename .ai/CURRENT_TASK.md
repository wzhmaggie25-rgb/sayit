# Current Task

> 最后一次更新：2026-06-29

## 状态

**ZCODE_READY**

---

## 当前结论

Round 9.4 **未通过独立审查**，不要开始用户实机验收，也不要恢复新需求开发。

用户又报告了三个真实生产问题：

1. 识别输出准确率很低，出现大量错字；
2. 已经出现文字后，悬浮窗最后仍显示“识别失败”；
3. 悬浮窗新增黄色“后台异常/后台已恢复”等技术提示，状态混乱。

代码审查已确认：

- streaming 最终文本目前只用“字数是否足够”判断质量，错误但够长的文本会直接被采用；
- 静默学习规则会进行全局字符串替换，坏规则可能继续破坏原始识别文本；
- `float.html` 把通用 error 统一显示成“识别失败”，无法区分 ASR、AI、注入和服务中断；
- Electron backend supervisor 会主动把“后台异常，SayIt 正在恢复”和“后台已恢复”显示成黄色提示；
- 后端出现该提示意味着进程确实异常退出并被自动重启，不能只当UI问题处理。

同时，Round 9.4 原有阻断仍然存在：

- streaming 每次新建 ThreadPoolExecutor，永久阻塞时会每次遗留一个不可取消线程；
- DashScope batch 和本地 ONNX/PyTorch 仍没有可终止的硬边界；
- ASR 第三个新测试反而断言旧的错误行为为通过；
- 前端所谓“生产处理器测试”只检查源码字符串，没有执行真实事件处理器；
- `pipeline_done` 仍独立停止 watchdog/重置浮窗；
- 修饰键释放仍可能释放 generic + side-specific 重复别名；
- 热键/native/fallback 计数仍在会话日志写完后才复制，并且是累计值而非单会话增量；
- no-target 早退仍可能保留上一会话目标元数据；
- 测试报告存在不存在的测试名称，缺少准确完整测试数量。

---

## 必须执行

本轮必须使用 **BDD + TDD**，不得再次先改实现、再补能通过的测试。

先完整阅读：

1. `.ai/ROUND9_5_TEST_INTEGRITY_RUNTIME_BOUNDARY_REVIEW.md`
2. `.ai/ROUND9_5_TEST_INTEGRITY_RUNTIME_BOUNDARY_TASK.md`
3. `.ai/ROUND9_5_BDD_ASR_ACCURACY_UI_RECOVERY_ADDENDUM.md`
4. `.ai/ROUND9_4_RUNTIME_CLOSURE_TASK.md`
5. 当前 Round 9.4 代码和测试

然后把以下两个任务作为**一个完整开发回合**执行：

```text
.ai/ROUND9_5_TEST_INTEGRITY_RUNTIME_BOUNDARY_TASK.md
.ai/ROUND9_5_BDD_ASR_ACCURACY_UI_RECOVERY_ADDENDUM.md
```

执行顺序：

1. 先提交 Gherkin/BDD 场景；
2. 再提交会在当前代码上失败的生产路径测试；
3. 再做最小生产修改；
4. 测试变绿后重构；
5. 最后跑完整回归并生成真实报告。

本轮必须同时完成：

- batch ASR 成为可用时的规范最终结果，streaming 只做进度/受控备用；
- 错误但够长的 streaming 结果不能绕过最终验证；
- 静默学习规则进入安全门/影子模式，不能大面积改坏句子；
- AI失败或超时时，有可用ASR文本就正常完成；
- “识别失败”只对应真正没有可用识别结果；
- 注入失败、服务中断、无目标、AI降级不得伪装成识别失败；
- 后台空闲时自动恢复必须静默，不再显示黄色“后台已恢复”；
- 活跃会话中后端崩溃必须产生唯一 `service_interrupted` 终止结果；
- 永久阻塞SDK/本地推理必须有真正可终止的进程或原生取消边界；
- 前端测试必须调用 main.js 实际使用的同一个生产控制器；
- 完成Native修饰键、单会话诊断、严格单终止事件和测试报告可信度收口。

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
- 不自动清空或删除用户已有静默学习规则/词典
- 不开发发布、登录、支付、订阅、更新器或其他产品功能
- 不通过过滤乱码/错字字符串掩盖问题
- 不通过 daemon 线程、线程改名、忽略线程计数来掩盖泄漏
- 不保留断言已知错误行为的测试
- 不用源码 grep 冒充生产路径测试
- 不虚构测试名称、数量或运行结果

---

## 完成门槛

完成后必须具备：

- BDD场景全部映射到可执行测试；
- 原始ASR、规则修正、AI整理、最终输出四层可分别验证；
- batch final、streaming fallback和无可用结果的选择行为确定且有测试；
- 静默规则和AI候选都不能破坏更好的上一层文本；
- 悬浮窗只有一个真实、易懂、无矛盾的最终状态；
- 空闲后台恢复无黄色提示；
- 永久provider/stop阻塞后，无残留线程或子进程；
- 后续会话和后端退出正常；
- 一个绝对 monotonic ASR deadline 覆盖 streaming、云端、本地加载和推理；
- 真实加载的Native DLL版本/build/path/hash证据；
- 受控Win32输入连续10次完全一致、无额外字符；
- 每条要求路径严格一个 terminal；
- `[SESSION]`记录正确单会话增量和不含正文的阶段质量指标；
- 完整测试准确 pass/skip/fail 数量与时长；
- `.ai/ROUND9_5_SELF_REVIEW.md`、PROJECT_STATE、TEST_RESULTS、ZCODE_REPORT全部真实更新。
