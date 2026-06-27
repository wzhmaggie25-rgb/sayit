# Current Task

> 最后一次更新：2026-06-27

## 状态

**ZCODE_READY**

> Round 5 提交 `bff31037d6992b421c60f91d41a515e1565a16ce` 未通过代码审查，不得进入用户验收。

## 任务名称

修复 Typeless 结果卡片、真实注入 readback、完整剪贴板保护，并完成重复纠错提升个人热词。

## 仓库与边界

- 仓库：`wzhmaggie25-rgb/sayit`
- 分支：`feature/silent-learning-stabilization`
- 本轮待修复基线：`bff31037d6992b421c60f91d41a515e1565a16ce`
- 稳定备份：commit `0d69a98`，tag `local-working-2026-06-25`
- 本地目录：`D:\code\sayit_zcode`
- 执行方式：ZCode GUI

不得修改 `main`、`backup/*` 或稳定 tag；不得 force push、`reset --hard`、`git clean`；不得读取或修改用户真实数据库、词典、历史、录音和私人文本。

## 开始前必须读取

按优先级依次读取：

```text
.ai/ROUND5_CODE_REVIEW.md
.ai/CURRENT_TASK_OVERRIDE.md
.ai/TYPELESS_RUNTIME_VALIDATION.md
```

`ROUND5_CODE_REVIEW.md` 是本轮直接执行清单，覆盖此前“已完成/等待验收”的结论。

## 必须修复的阻塞项

1. 结果卡片不能依赖未加载的 React；优先改为离线可运行的原生 HTML/CSS/JS；
2. 修复窗口首次创建时 `result_card_show` payload 在 ready 前丢失；
3. `Ctrl+V`/SendInput 已发送绝不能直接标记 verified；verified 只能来自目标控件 readback；
4. 增加 `attempted_unverified`，且不可验证后不得盲目走第二条输入路径；
5. 原剪贴板为空时必须恢复为空；
6. 检测到图片、文件、HTML、RTF、多格式或未知格式时，不得使用会破坏剪贴板的 paste 路径；
7. 结果卡片必须展示最近转录信息和 final_text 两层内容，关闭按钮在右上角；
8. no_editable_target / attempted_unverified / injection_failed 不得启动 SilentMonitor；
9. 重新实现可靠的当前输入焦点/可编辑性判断，不得把 TextPattern 存在等同于可编辑；
10. 结果卡片复制改为 Electron IPC，从主进程受信任 pending text 复制，不接受 renderer 任意 text REST 请求；
11. 完成重复纠错跨不同 history 安全提升为个人热词，不得再次推迟；
12. `.ai/ZCODE_REPORT.md` 必须写入最终真实完整 commit SHA。

详细根因、代码位置、测试要求见：

```text
.ai/ROUND5_CODE_REVIEW.md
```

## 产品规则

### 正常成功输入

- final_text 进入当前有效输入框；
- 不把 final_text 留在剪贴板；
- 内部若临时借用剪贴板，最终必须恢复原状态；
- 不弹结果卡片。

### 无有效输入目标

- 不强抢焦点恢复旧输入框；
- 不自动复制；
- 保留原剪贴板；
- 弹出大结果卡片；
- 用户点击复制后才写入 final_text；
- 显示绿色勾后关闭。

### 不可验证输入

- 状态为 `attempted_unverified`；
- 不得标记 verified；
- 不得再盲目 SendInput 造成双份文字；
- 不启动静默学习。

### 真正识别失败

只有没有产生 final_text 时才使用 `recognition_failed`。

## 必须完成的个人热词提升

- 同一 `(pattern, replacement)` 在两个不同 history 后才提升；
- 同一 history 不重复计数；
- 只有 replacement 入词典；
- 冲突、平票、接近竞争不提升；
- 整句、追加、多处修改、长短语不提升；
- 单次最多提升一个词；
- 重复扫描幂等；
- 提升后同步 HotwordsManager/ASR；
- 不清洗或改写用户已有词典。

## 验证

必须运行：

```text
python -m pytest tests/ -v --timeout=30
node --check frontend/main.js
```

并增加：

- result-card 离线 smoke test；
- 首次 ready payload 不丢失测试；
- 空剪贴板恢复为空测试；
- 非文本/多格式不被破坏测试；
- readback verified/unverified/failed 测试；
- attempted_unverified 不重复注入测试；
- no target 不启动 SilentMonitor 测试；
- 两个不同 history 后提升热词及冲突/幂等测试。

## 交付

更新：

```text
.ai/ZCODE_REPORT.md
.ai/TEST_RESULTS.md
.ai/PROJECT_STATE.md
```

完成后：

1. commit 并 push 当前 feature 分支；
2. 报告写入真实完整 SHA；
3. 远端 HEAD 与报告一致；
4. 状态改为 `BLOCKED_USER_VALIDATION`。
