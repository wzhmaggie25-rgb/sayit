# SayIt Product Requirements Baseline

> 日期：2026-06-27
> 用途：保存前几轮已经确认的软件产品需求，后续每轮开发不得只看 CURRENT_TASK，必须同时读取本文件。

## 一、产品定位

SayIt 是 Windows 本地语音输入软件：

- 用户按右 Alt 开始/停止录音；
- 语音经 ASR、热词、本地纠错和可选 AI 整理；
- 文本安全输入当前可编辑位置；
- 无有效输入位置时提供可复制结果；
- 在安全条件下观察用户后续纠错，逐步学习个人热词和纠错偏好；
- 后续扩展场景化写作、用户账号、发布升级与社群入口。

核心产品原则：

```text
不丢文字
不覆盖原文
不重复输入
不污染剪贴板
不抢错焦点
不把不确定说成成功
不把偶然修改学成永久规则
```

## 二、录音与快捷键

- 右 Alt 是唯一主快捷键；
- 一次按下开始，再按一次停止；
- 停止反馈必须即时；
- 长录音也必须一次停止；
- 热键事件不得传给前台软件激活菜单或破坏输入焦点；
- ASR/AI/注入期间再次按键不得启动并发 Pipeline；
- 保留 RAltStopWatcher 和 native keyboard helper，但允许为可靠性优化实现。

## 三、悬浮窗

### 条形悬浮窗

- 位于当前屏幕底部附近；
- 不抢焦点；
- 展示录音、停止、识别、AI 整理、注入和错误状态；
- 鼠标只在真实可见控件范围内可点击；透明区域穿透。

### 结果卡片（最新修订）

只在：

```text
没有有效输入焦点
AND 没有发送任何注入动作
AND 本次文本确定没有输入
```

时显示。

要求：

- 比条形悬浮窗大，但不是屏幕中间的大对话框；
- 默认约 360px 宽，按内容动态高度；
- 位于条形悬浮窗上方；
- 不抢焦点；
- 展示最终文本、状态、复制和关闭；
- 只有用户点击复制才写剪贴板；
- 新录音开始必须清理旧卡片和旧 payload；
- attempted_unverified 不弹大卡片，只用轻提示。

## 四、注入状态契约

合法状态：

```text
verified_success
attempted_unverified
no_editable_target
injection_failed
recognition_failed
```

### verified_success

- 只能来自同一 focused control 的真实 readback；
- 必须验证 pre/selection/post 与本次插入完全一致；
- 不能由 shortcut dispatch、SendInput count、clipboard 状态或 substring 推断；
- 只有该状态可启动 SilentMonitor。

### attempted_unverified

- 已发送动作，但无法证明结果；
- 不得盲目尝试第二条注入路径；
- 不得启动 SilentMonitor；
- 不自动弹大结果卡片。

### no_editable_target

- 没有有效 focused editable control；
- 不触碰剪贴板；
- 不抢回任意历史窗口；
- 满足最新 eligibility 时显示结果卡片。

### injection_failed

- 有可靠证据证明目标未变化或动作失败；
- 不重复尝试可能造成重复输入的路径；
- 保存历史和诊断。

## 五、焦点与输入位置

- 录音开始捕获目标仅用于诊断和 identity；
- 注入时重新验证当前 focused control；
- 用户主动切换到新的有效输入框时，使用新输入框；
- 不强抢任意旧窗口；
- 可以为防止 Alt 热键自身造成的瞬时菜单失焦，恢复“停止键按下前刚验证过的同一 control”，但不能恢复更早的 stale target；
- SayIt 自己的主窗口、条形悬浮窗、结果卡片必须排除。

Win32 Edit/RichEdit：

- GetGUIThreadInfo 获取真实 hwndFocus；
- EM_GETSEL + EM_REPLACESEL；
- 保留选区外前后文。

UIA/Chromium/Electron：

- 不使用 ValuePattern.SetValue 覆盖整字段；
- 无 selection-aware 安全写入时走 clipboard/SendInput 或保守失败；
- 不确定时不声称 verified。

## 六、剪贴板保护

四态 snapshot：

```text
EMPTY
TEXT
UNSUPPORTED_OR_MULTIFORMAT
READ_FAILED
```

- EMPTY 恢复为空；
- TEXT 恢复原文本；
- 图片、文件、HTML、RTF、多格式不得被破坏；
- 无法安全恢复时不使用 clipboard path；
- restore 失败必须如实写入 InjectionResult；
- `copy_result_to_clipboard=false` 默认；
- 只有结果卡片用户主动点击复制才写最终文本。

## 七、ASR 与 AI 整理

- 保留实时 ASR + cascade fallback；
- 流式结果质量不足时允许 batch fallback；
- 热词保护优先；
- AI 整理支持 none/light/deep；
- none 模式保留原话；
- AI 失败或超时必须降级到本地纠错文本，不能卡死；
- AI 不得修改受保护热词、路径、命令、代码标识；
- 后续加入场景化整理和个人表达档案。

## 八、静默学习

启动条件：

```text
verified_success
AND target_verified
AND same input identity
```

- 观察窗口默认 15 秒，可后续调整；
- 切换窗口、切换输入框、清空、大幅重写、锚点丢失时跳过；
- 同一 history 重放完全幂等；
- 普通纠错规则至少 3 次证据后才自动应用；
- 个人热词至少 2 个不同 history；
- 2 vs 1 冲突不提升；
- 只提升 replacement，不提升错误 pattern；
- 单次最多一个热词；
- 单次修改不得绕过 promotion engine 直接入词典；
- ASR sync 成功后才能标记 promoted；
- 后续提供学习中心：查看、暂停、修改、删除、撤销、限制作用范围。

## 九、场景化与 Typeless 对标方向

后续按顺序开发：

1. ContextSnapshot 和场景分类；
2. 场景提示词；
3. 纠错规则 scope（全局/应用/场景/上下文）；
4. shadow mode；
5. 个人表达档案；
6. 选中文字语音编辑；
7. 翻译、总结、解释、格式化；
8. 自我纠正和更完整重复消除。

不能在运行时稳定性未通过前展开大规模新能力。

## 十、结果可见性和恢复

- 历史保存 ASR 原文、本地整理、AI 最终文本、目标应用、注入状态和错误；
- 用户可以从历史恢复；
- 错误或崩溃不得自动重复注入；
- 后台 crash 后 UI 必须退出“思考中”；
- 默认诊断不保存完整私人正文和凭据。

## 十一、开发和 Git 安全

- 当前稳定备份：`0d69a98`；
- 稳定 tag：`local-working-2026-06-25`；
- 不修改 main、backup/*、稳定 tag，除非用户明确批准合并；
- 不 force push、reset --hard、git clean；
- 不读取或修改真实用户数据库、词典、历史、录音、日志正文、API key；
- 每轮任务先写需求、失败测试和验收标准；
- 自动测试通过不等于实机验收通过；
- 长任务优先 Bridge，Bridge 故障或修 Bridge 自身时用 ZCode。

## 十二、商业化与发布需求（已记录，尚未开发）

- 微信扫码登录；
- 用户账号、设备和会话；
- 官网/下载页；
- Windows 安装包；
- 版本检查、下载、升级和回滚；
- 用户加入微信群/客服群入口；
- 后续授权、试用、订阅和云同步。

这些功能必须在运行时稳定性和隐私边界明确后，放到新分支独立开发。