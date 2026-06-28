# Current Task

> 最后一次更新：2026-06-28

## 状态

**ZCODE_READY**

## 结论

Round 9 自审不能作为完成依据。ChatGPT 独立代码审查发现多个生产路径与测试不一致的问题，当前不得进入用户实机验收，不得合并 main。

## 必须读取

```text
AGENTS.md
.ai/PRODUCT_REQUIREMENTS_BASELINE.md
.ai/ROUND9_CODE_REVIEW.md
.ai/ROUND9_1_FIX_TASK.md
.ai/ROUND9_LONG_TASK.md
.ai/ROUND9_SELF_REVIEW.md
```

其中：

```text
.ai/ROUND9_CODE_REVIEW.md
.ai/ROUND9_1_FIX_TASK.md
```

优先级最高。

## 当前已确认问题

1. 结果卡片把 float viewport 坐标误当屏幕坐标；
2. 严格弹卡资格只存在于测试文件，生产 Pipeline 没使用；
3. RAlt watcher 在 keydown 停止，但 native helper 在 keyup 再 emit toggle；
4. stop latch 检查/设置非原子；
5. 焦点恢复发生在注入完成后并会无条件抢回旧窗口；
6. Session ID 在 broadcast 时从全局补写，迟到事件可能被标成新 session；
7. Backend supervisor 生产代码与测试模拟不一致，正常 exit code 0 也会重启；
8. AI timeout 会遗留不可取消 daemon request thread；
9. 多个新增测试只是重写常量/公式/模拟 dict，没有执行生产实现；
10. 全量测试仍有4失败，并通过 deselect/timeout变化绕开了原任务门禁。

## 执行器

```text
ZCode GUI → Claude Code
```

Agent Bridge保持关闭。

## 唯一任务

严格执行：

```text
.ai/ROUND9_1_FIX_TASK.md
```

Phase A 到 Phase H 连续自主完成。

必须：

- 先写调用真实生产路径的失败测试；
- 修复真实生产实现；
- 删除或重写镜像逻辑/手工模拟型伪测试；
- 每个 Phase checkpoint commit + push；
- 不向用户询问普通实现细节。

## 安全边界

- 不修改 main、backup/*、稳定 tag；
- 不 force push、reset --hard、git clean；
- 不读取或修改真实用户数据库、历史、词典、录音、正文、API key；
- 不重复注入；
- 不破坏剪贴板；
- 不抢用户主动切换后的焦点；
- 不开发微信登录、安装、升级、群聊、订阅、场景化写作。

## 完成门禁

以下命令必须原样运行且 0 failures：

```text
python -m pytest tests/ -v --timeout=30
node --check frontend/main.js
node --check frontend/preload.js
node frontend/_smoke_result_card.js
```

不得 deselect。

必须创建：

```text
.ai/ROUND9_1_SELF_REVIEW.md
```

成功终态：

```text
BLOCKED_USER_VALIDATION
```

最终填写每个 checkpoint 完整 SHA 和真实远端 HEAD，commit并push。