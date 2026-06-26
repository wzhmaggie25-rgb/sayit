// WH_KEYBOARD_LL hook DLL for Sayit - RAlt toggle (Typeless architecture, v2).
//
// Architecture rationale
// ----------------------
// Windows enforces a soft LowLevelHooksTimeout (~300 ms by default) on
// WH_KEYBOARD_LL hook procedures. If the HookProc takes longer than this,
// Windows silently UNHOOKS us — and the *next* key press goes through.
// Users then see "second RAlt does nothing".
//
// The first cut of this DLL invoked a ctypes Python callback DIRECTLY from
// the HookProc (`g_callback()` on the hook thread). Even though the Python
// wrapper spawned a daemon thread inside that callback, the call sequence
// still required:
//   1. Marshalling argument-less call back into the Python interpreter.
//   2. Acquiring the GIL.
//   3. Constructing the threading.Thread object.
// Under heavy GIL contention (long recordings → ASR streaming, audio chunk
// callbacks, RMS callbacks, etc.) that round-trip CAN exceed 300 ms, and
// the hook gets silently unloaded.
//
// v2 fix: the HookProc never touches Python and never waits for the GIL.
// It only does constant-time pure Win32 work:
//   * read kbd struct, update g_matched
//   * (on RAlt up) increment a lock-free atomic counter + SetEvent
//   * (on RAlt up) ForceReleaseAlt — pure SendInput, no Python
// A dedicated native worker thread blocks on the auto-reset event and
// invokes the Python callback FROM ITS OWN CONTEXT. Even if the callback
// hangs for seconds, the hook thread is never blocked.
//
// Exports
// -------
//   install_hook(callback)         install hook + spawn worker thread
//   uninstall_hook()               stop worker, drain events, uninstall
//   is_hook_installed()
//   get_pending_count()            number of toggles emitted but not yet
//                                  consumed by the worker (testing aid)
//   get_total_emitted()            total toggles emitted since install
//   get_total_consumed()           total toggles consumed by worker since install
//   __test_trigger_toggle()        test-only: simulate a HookProc-side
//                                  toggle WITHOUT invoking Python from the
//                                  caller's thread. Used by stress tests
//                                  to verify the C++→Python transport.
//                                  This entry point is intentionally not
//                                  reachable from physical keys.

#include <windows.h>
#include <thread>
#include <atomic>

#ifdef __cplusplus
extern "C" {
#endif

// ── VK constants ────────────────────────────────────────────────────
#define VK_RMENU    0xA5
#define VK_LMENU    0xA4
#define VK_MENU     0x12
#define LL_HOOK     13
#ifndef KF_UP
#define KF_UP       0x0002
#endif

// ── Hook state (process-global singleton) ───────────────────────────
static HHOOK                g_hHook = nullptr;
static std::thread          g_hookThread;
static DWORD                g_hookThreadId = 0;
static std::thread          g_workerThread;
static DWORD                g_workerThreadId = 0;
static std::atomic<bool>    g_running{false};
static bool                 g_matched = false;

// Worker-thread synchronization (HookProc → worker → Python)
// ---------------------------------------------------------
// g_toggleEvent is auto-reset — every SetEvent wakes one waiter or arms one.
// g_pending counts toggles emitted but not yet drained by the worker so we
// can never lose a wakeup even if SetEvent and Wait race.
static HANDLE                       g_toggleEvent = nullptr;
static std::atomic<unsigned long>   g_pending{0};
static std::atomic<unsigned long>   g_total_emitted{0};
static std::atomic<unsigned long>   g_total_consumed{0};

// Callback function pointer (set by install_hook).
// CRITICAL: this is called ONLY from the worker thread, NEVER from HookProc.
static void                 (*g_callback)(void) = nullptr;

static void D(const char* msg) {
    OutputDebugStringA("[keyboard-helper] ");
    OutputDebugStringA(msg);
    OutputDebugStringA("\n");
}

// ── Native helpers ──────────────────────────────────────────────────

static void ForceReleaseAlt() {
    // Unconditionally release all three Alt VKs. Pure SendInput — no Python,
    // no GIL, safe to call from HookProc.
    UINT vks[] = {VK_RMENU, VK_LMENU, VK_MENU};
    for (int i = 0; i < 3; i++) {
        INPUT inp = {};
        inp.type = INPUT_KEYBOARD;
        inp.ki.wVk = static_cast<WORD>(vks[i]);
        inp.ki.dwFlags = KEYEVENTF_KEYUP;
        SendInput(1, &inp, sizeof(INPUT));
    }
}

// Emit a toggle: increment counter + signal event. Constant time, no Python.
static void EmitToggle() {
    g_pending.fetch_add(1, std::memory_order_release);
    g_total_emitted.fetch_add(1, std::memory_order_relaxed);
    if (g_toggleEvent) {
        SetEvent(g_toggleEvent);
    }
}

// ── Hook procedure (called on the hook thread) ──────────────────────
//
// MUST be constant-time, MUST NOT acquire the Python GIL, MUST NOT call
// any Python/ctypes callback. The only work permitted here:
//   - read kbd struct fields
//   - update g_matched
//   - call SendInput (pure Win32) for stuck-Alt cleanup
//   - call EmitToggle (atomic + SetEvent)
//   - return CallNextHookEx or 1 to swallow the event
//
static LRESULT CALLBACK HookProc(int nCode, WPARAM wParam, LPARAM lParam) {
    if (nCode < 0)
        return CallNextHookEx(nullptr, nCode, wParam, lParam);

    KBDLLHOOKSTRUCT& kbd = *reinterpret_cast<KBDLLHOOKSTRUCT*>(lParam);
    UINT vk = static_cast<UINT>(kbd.vkCode);
    DWORD flags = kbd.flags;

    // Drop synthetic input (our own SendInput must not re-enter the hook).
    if (flags & LLKHF_INJECTED)
        return CallNextHookEx(nullptr, nCode, wParam, lParam);

    bool isDown = (wParam == WM_KEYDOWN || wParam == WM_SYSKEYDOWN);
    bool isUp   = (wParam == WM_KEYUP   || wParam == WM_SYSKEYUP);
    bool isMain = (vk == VK_RMENU || vk == VK_MENU);

    if (vk == VK_MENU) {
        vk = (flags & LLKHF_EXTENDED) ? VK_RMENU : VK_LMENU;
        isMain = (vk == VK_RMENU);
    }

    if (!g_matched) {
        if (isMain && isDown) {
            g_matched = true;
            // Preemptive release: when the hook eats RAlt, the driver may have
            // already armed VK_MENU / VK_LMENU async state. Release them so
            // they don't get stuck for the entire recording session.
            if (GetAsyncKeyState(VK_MENU) & 0x8000) {
                INPUT inp = {}; inp.type = INPUT_KEYBOARD;
                inp.ki.wVk = VK_MENU; inp.ki.dwFlags = KEYEVENTF_KEYUP;
                SendInput(1, &inp, sizeof(INPUT));
            }
            if (GetAsyncKeyState(VK_LMENU) & 0x8000) {
                INPUT inp = {}; inp.type = INPUT_KEYBOARD;
                inp.ki.wVk = VK_LMENU; inp.ki.dwFlags = KEYEVENTF_KEYUP;
                SendInput(1, &inp, sizeof(INPUT));
            }
            return 1; // eat the key
        }
        if (isMain && isUp) {
            return 1; // eat stray RAlt up
        }
    } else {
        if (isMain && isUp) {
            g_matched = false;
            // Emit toggle on the rising edge of release. The HookProc returns
            // immediately; the worker thread will run the Python callback.
            EmitToggle();
            ForceReleaseAlt();
            return 1;
        }
        if (isMain && isDown) {
            // Auto-repeat keydown while held: swallow but never duplicate.
            return 1;
        }
    }

    return CallNextHookEx(nullptr, nCode, wParam, lParam);
}

// ── Worker thread: drains pending toggles and invokes Python callback ──
//
// Lives outside the hook thread so callback latency is decoupled from the
// LowLevelHooksTimeout deadline. The worker holds the only reference to
// g_callback (besides install_hook/uninstall_hook which serialize via the
// Python-side install lock).
static void WorkerThread() {
    g_workerThreadId = GetCurrentThreadId();
    while (g_running.load(std::memory_order_acquire)) {
        DWORD r = WaitForSingleObject(g_toggleEvent, 200);
        if (!g_running.load(std::memory_order_acquire)) break;
        if (r != WAIT_OBJECT_0 && r != WAIT_TIMEOUT) break;
        // Drain as many emitted toggles as we can see; each consumption
        // calls into Python exactly once. This is safe under heavy load:
        // missed wakeups can't happen because g_pending is checked
        // unconditionally after the wait returns.
        while (true) {
            unsigned long pending = g_pending.load(std::memory_order_acquire);
            if (pending == 0) break;
            if (!g_pending.compare_exchange_strong(
                    pending, pending - 1,
                    std::memory_order_acq_rel, std::memory_order_acquire)) {
                continue;
            }
            void (*cb)(void) = g_callback;
            if (cb) {
                // From the worker thread, calling Python is safe — the hook
                // thread has already returned to Windows long ago.
                cb();
            }
            g_total_consumed.fetch_add(1, std::memory_order_relaxed);
        }
    }
    g_workerThreadId = 0;
}

// ── Hook thread: owns the hook and message pump ─────────────────────

static void HookThread() {
    g_hookThreadId = GetCurrentThreadId();

    g_hHook = SetWindowsHookEx(WH_KEYBOARD_LL, HookProc, GetModuleHandle(nullptr), 0);
    if (!g_hHook) {
        D("HookThread: SetWindowsHookEx FAILED");
        g_running = false;
        return;
    }
    D("HookThread: hook installed OK");

    MSG msg;
    while (g_running.load(std::memory_order_acquire) &&
           GetMessage(&msg, nullptr, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }

    if (g_hHook) {
        UnhookWindowsHookEx(g_hHook);
        g_hHook = nullptr;
        D("HookThread: hook uninstalled");
    }
    g_matched = false;
    g_hookThreadId = 0;
}

// ── Exported API ────────────────────────────────────────────────────

__declspec(dllexport) int install_hook(void* callback_ptr) {
    if (callback_ptr == nullptr) {
        D("install_hook: callback_ptr is null");
        return 0;
    }

    if (g_running.load()) {
        D("install_hook: already running");
        return 0;
    }

    g_matched = false;
    g_callback = reinterpret_cast<void(*)()>(callback_ptr);
    g_pending.store(0);
    g_total_emitted.store(0);
    g_total_consumed.store(0);

    if (!g_toggleEvent) {
        g_toggleEvent = CreateEventA(nullptr, FALSE, FALSE, nullptr);  // auto-reset
        if (!g_toggleEvent) {
            D("install_hook: CreateEvent FAILED");
            g_callback = nullptr;
            return 0;
        }
    } else {
        ResetEvent(g_toggleEvent);
    }

    g_running.store(true, std::memory_order_release);

    g_workerThread = std::thread(WorkerThread);
    g_hookThread = std::thread(HookThread);

    // Wait up to 500ms for hook to install
    for (int i = 0; i < 50; i++) {
        if (g_hHook) break;
        Sleep(10);
    }

    if (!g_hHook) {
        // Hook never came up. Tear down the worker too so we don't leak it.
        g_running.store(false, std::memory_order_release);
        SetEvent(g_toggleEvent);
        if (g_hookThread.joinable()) g_hookThread.join();
        if (g_workerThread.joinable()) g_workerThread.join();
        g_callback = nullptr;
        D("install_hook: FAILED");
        return 0;
    }

    D("install_hook: OK");
    return 1;
}

__declspec(dllexport) int uninstall_hook(void) {
    D("uninstall_hook: stopping hook");

    if (!g_running.exchange(false, std::memory_order_acq_rel)) {
        // Already torn down — nothing more to do.
        return 1;
    }

    // Tell the worker to wake and exit even if no toggles are pending.
    if (g_toggleEvent) SetEvent(g_toggleEvent);

    // Wake the hook thread from GetMessage so it can exit.
    DWORD tid = g_hookThreadId;
    if (tid != 0) {
        PostThreadMessage(tid, WM_QUIT, 0, 0);
    }

    // Join both threads — guarantees no in-flight callback after return.
    if (g_hookThread.joinable()) {
        try { g_hookThread.join(); } catch (...) {}
    }
    if (g_workerThread.joinable()) {
        try { g_workerThread.join(); } catch (...) {}
    }

    // Now safe to drop the callback: no thread can reference it any more.
    g_callback = nullptr;
    g_pending.store(0);

    return 1;
}

__declspec(dllexport) int is_hook_installed(void) {
    return (g_running.load() && g_hHook != nullptr) ? 1 : 0;
}

__declspec(dllexport) unsigned long get_pending_count(void) {
    return g_pending.load(std::memory_order_acquire);
}

__declspec(dllexport) unsigned long get_total_emitted(void) {
    return g_total_emitted.load(std::memory_order_relaxed);
}

__declspec(dllexport) unsigned long get_total_consumed(void) {
    return g_total_consumed.load(std::memory_order_relaxed);
}

// ── Test-only entry point ───────────────────────────────────────────
//
// Simulates an emit from the HookProc WITHOUT a physical key, so the
// transport from native producer → worker thread → Python callback can
// be stress-tested. Behavior is exactly what HookProc does on RAlt-up
// minus the SendInput cleanup — we only touch the lock-free counter and
// the auto-reset event. Physical keys never reach this entry point; it
// is reachable only from Python via ctypes for tests.
__declspec(dllexport) int __test_trigger_toggle(void) {
    if (!g_running.load()) {
        return 0;
    }
    EmitToggle();
    return 1;
}

#ifdef __cplusplus
}
#endif
