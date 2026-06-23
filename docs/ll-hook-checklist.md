# WH_KEYBOARD_LL 钩子攻坚清单

> 记录 Sayit 右 Alt 全局快捷键修复过程中踩过的坑。每个坑单独可复现、单独可诊断。

---

## 1. 钩子未安装：pynput win32_event_filter 不拦截 OS 事件

**现象**：日志显示 filter 判定 SUPPRESS，但事件仍进系统（菜单激活、按键漏字）。

**根因**：pynput `Keyboard._convert()`:
```python
if self._event_filter(msg, data) is False:
    return None  # 只跳过 on_press/on_release，不拦截 OS
```
Windows `LowLevelKeyboardProc` 中真正拦截靠 `SuppressException` → `return 1`，但 filter 返回 False 时从未抛此异常。

**诊断**：在 `_hook_proc` 加日志，确认 `return 1` 是否被执行；检查 pynput 的 `SystemHook._handler`。
```python
# pynput: SystemHook._handler (win32.py:299-313)
try: self.on_hook(...)
except SuppressException: return 1  # 只有这里才拦截
return CallNextHookEx(...)          # 否则放行
```

**修复**：用原生 ctypes `SetWindowsHookEx(WH_KEYBOARD_LL)` 替代 pynput。Hook proc 返回 `1` 直接拦截。

---

## 2. 钩子回调永不触发：线程错位

**现象**：钩子装上了（`hHook != NULL`），但 `_hook_proc` 从未被调用。按任意键无日志。

**根因**：`WH_KEYBOARD_LL` 的回调派发到**调用 `SetWindowsHookEx` 的那个线程**，该线程必须跑 `GetMessage` 泵。如果安装和泵在不同线程 → 永不回调。

```
错误模式：
  Thread A: SetWindowsHookEx(...)     ← 安装
  Thread B: while: GetMessage(...)    ← 泵（无效！）

正确模式：
  Thread A: SetWindowsHookEx(...)     ← 安装
            while: GetMessage(...)    ← 泵（同线程）
```

**诊断**：打印 `SetWindowsHookEx` 所在线程 vs `GetMessage` 所在线程的 thread ID。

**修复**：见 `infrastructure/hotkey.py:_hook_thread()`——定义 hook proc → 安装 → 消息泵，全部在同一方法、同一线程。

---

## 3. 状态机变量不同步：局部 s 未更新

**现象**：第一次 toggle 正常，第二次按触发键无反应（toggle 不翻转）。

**根因**：
```python
s = self._state  # 读一次

# ... IDLE_DEBOUNCE 分支改了 self._state = 'IDLE' ...
# 但 s 没更新！

if s == 'IDLE':  # s 仍是 'IDLE_DEBOUNCE' → False → 跳过
```

**修复**：去掉 `IDLE_DEBOUNCE` 状态，用 `_last_toggle_ts` 时间戳防抖。`_do_toggle()` 后直接 `_state = IDLE`。

---

## 4. 不对称 suppress：bounce 分支吞 down 但漏 up

**现象**：右 Alt 按下后松开，Alt 卡在 OS → 后续按键全变 Alt+key 快捷组合 → 菜单加速键/乱码。

**根因**：IDLE 的 bounce 分支 suppress down（`return False`）但未进 MATCHED。up 事件到 IDLE 找不到对应分支 → `return True` → 泄漏 → OS 只剩 Alt up 没有 Alt down → 状态混乱。

**修复**：删除 IDLE bounce suppression 分支。Mode B IDLE 中对 `is_main && _is_up` 也 suppress（stray up）。

---

## 5. 返回值类型不匹配：`is False` vs `not`

**现象**：filter 返回 None/0/空字符串时被当作 suppress。

**根因**：Python 中 `not None`、`not 0`、`not ""` 都是 `True`。
```python
if not self._win32_filter(...):  # BUG：非布尔值时语义错误
    return 1
```

**修复**：使用 `is False` / `is True` 精确比较。非布尔值打 warning 并按 pass 处理。

---

## 6. vkE8 mask key（保底）

**场景**：即使 hook suppress 正常工作，某些应用（高权限/特殊消息处理）仍可能收到 Alt 事件。

**方案**：检测到右 Alt 按下时，立即注入 `vkE8` (0xE8，微软标记"unassigned") 虚拟键：
```python
ctypes.windll.user32.keybd_event(0xE8, 0, 0, 0)         # down
ctypes.windll.user32.keybd_event(0xE8, 0, 0x0002, 0)     # up
```
注入的事件的 `LLKHF_INJECTED` 标志会让 hook 放行。OS 看到 Alt↓ → vkE8↓↑ → Alt↑，判定"有中间键，非单独 Alt" → 不发 `SC_KEYMENU`。

**来源**：Typeless 实测通过；闪电说同法；AutoHotkey `A_MenuMaskKey`。

---

## 7. HOOKPROC 被 GC

**现象**：钩子装上一段时间后失效（无日志、无回调）。

**根因**：`ctypes.WINFUNCTYPE` 包装的 Python 函数必须用强引用保持存活。如果引用消失 → GC 回收 → Windows 调回调时访问已释放内存 → 未定义行为。

**修复**：`self._hook_proc_ref = _hook_proc` 确保 HotkeyManager 存活期间回调不回收。

---

## 诊断速查

| 症状 | 检查 |
|------|------|
| 钩子装不上 | `hHook` 是否 NULL、`GetLastError()` |
| 装上了但不回调 | 安装线程 == 泵线程？`GetMessage` 是否在跑？ |
| 回调了但不拦截 | `_hook_proc` 是否 `return 1`？类型 `is False` 检查 |
| 拦截了但菜单还弹 | vkE8 mask key 注入了吗？Alt 事件是否有对称 suppress？ |
| 第一次 toggle 正常、第二次无效 | 状态机 s 变量同步问题 / bounce 不对称 |
