// WH_KEYBOARD_LL hook DLL for Sayit - RAlt toggle (Typeless architecture, v3).
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
// Under heavy GIL contention (long recordings -> ASR streaming, audio chunk
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
// v3 (2026-06-26-v3):
//   * Adds a 128-slot native diagnostics ring buffer that records every
//     keyboard event entering HookProc, BEFORE and AFTER the state-machine
//     parser runs. This lets us definitively distinguish:
//       - "HookProc never received the event" (no ring entry)
//       - "received but not matched/emitted" (entry with emitted=0)
//       - "emitted but Python didn't consume" (entry with emitted=1)
//     The ring is exported via `__test_native_diagnostics` as a struct
//     array — no text, only integer/enum/timestamp metadata.
//   * Exposes diagnostics to Python: `native_event_count` and
//     `native_events(limit)`.
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
//                                  to verify the C++->Python transport.
//                                  This entry point is intentionally not
//                                  reachable from physical keys.
//   __test_handle_event()          test-only: drive HandleKeyEventCore
//   __test_reset_state()           test-only: clear g_matched
//   native_event_count()           number of events recorded in ring
//   native_events(out, max)        copy up to max entries to caller buffer

#include <windows.h>
#include <thread>
#include <atomic>
#include <cstdint>

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

// ── Native diagnostics ring buffer ──────────────────────────────────
//
// Records every keyboard event that reaches HookProc. A consumer (Python)
// can read the ring to determine whether a suspected second RAlt was
// delivered to HookProc at all, or was dropped between the OS and our
// callback. No text or personal data is stored — only Win32 event codes
// and state-machine metadata.
//
#define NATIVE_DIAG_RING_SIZE 128

struct NativeEventRecord {
    // Monotonic sequence number (1-based, wraps at UINT32_MAX)
    uint32_t    seq;
    // Values from KBDLLHOOKSTRUCT
    uint32_t    vkCode;
    uint32_t    wParam;      // WM_KEYDOWN / WM_KEYUP / WM_SYSKEYDOWN / WM_SYSKEYUP
    uint32_t    flags;       // LLKHF_* flags (LLKHF_EXTENDED, LLKHF_INJECTED, etc.)
    // State-machine snapshot BEFORE HandleKeyEventCore
    uint32_t    matched_before; // g_matched before parse (0/1)
    // State-machine snapshot AFTER HandleKeyEventCore
    uint32_t    matched_after;  // g_matched after parse (0/1)
    // Did this event cause an EmitToggle?
    uint32_t    emitted;        // 0/1
    // Monotonic OS tick at the moment HookProc entered (GetTickCount64)
    uint64_t    tick_ms;
};

static NativeEventRecord  g_native_ring[NATIVE_DIAG_RING_SIZE];
static uint32_t           g_native_seq = 0;      // next seq (never decremented)
static uint32_t           g_native_write = 0;    // next write slot (mod NATIVE_DIAG_RING_SIZE)

// ── Hook state (process-global singleton) ───────────────────────────
static HHOOK                g_hHook = nullptr;
static std::thread          g_hookThread;
static DWORD                g_hookThreadId = 0;
static std::thread          g_workerThread;
static DWORD                g_workerThreadId = 0;
static std::atomic<bool>    g_running{false};
static bool                 g_matched = false;
static bool                 g_emitted_this_press = false;

// Worker-thread synchronization (HookProc -> worker -> Python)
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

// ── Native diagnostics helpers ─────────────────────────────────────

static void RecordNativeEvent(UINT vk, WPARAM wParam, DWORD flags,
                               uint32_t matched_before, uint32_t matched_after,
                               uint32_t emitted) {
    uint32_t seq = ++g_native_seq;          // starts at 1
    uint32_t slot = g_native_write++ % NATIVE_DIAG_RING_SIZE;
    g_native_ring[slot].seq = seq;
    g_native_ring[slot].vkCode = static_cast<uint32_t>(vk);
    g_native_ring[slot].wParam = static_cast<uint32_t>(wParam);
    g_native_ring[slot].flags = static_cast<uint32_t>(flags);
    g_native_ring[slot].matched_before = matched_before;
    g_native_ring[slot].matched_after = matched_after;
    g_native_ring[slot].emitted = emitted;
    g_native_ring[slot].tick_ms = GetTickCount64();
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

// ── Core keyboard-event parser (shared by HookProc and the test entry) ──
//
// Returns true if the event was consumed (would swallow / "eat the key"),
// false if the caller should pass through (CallNextHookEx).
//
// `allowSideEffects`: when false (test path) we skip SendInput-based stuck-
// Alt cleanup so unit tests do not inject real keystrokes into the OS. The
// state-machine transitions (g_matched, EmitToggle) are unchanged.
//
// MUST be constant-time, MUST NOT acquire the GIL, MUST NOT call back into
// Python — only the worker thread does that.
static bool HandleKeyEventCore(UINT vk, WPARAM wParam, DWORD flags,
                               bool allowSideEffects) {
    // Drop synthetic input (our own SendInput must not re-enter the hook).
    if (flags & LLKHF_INJECTED)
        return false;

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
            g_emitted_this_press = true;
            // v4: Emit on EVERY RAlt down — including the first press that
            // starts recording. The watcher also detects down-edge, so the
            // hook must increment total_emitted on the down-edge to let the
            // watcher verify the hook processed the event.
            EmitToggle();
            if (allowSideEffects) {
                // Preemptive release: when the hook eats RAlt, the driver may
                // have already armed VK_MENU / VK_LMENU async state. Release
                // them so they don't stay stuck for the whole session.
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
            }
            return true; // eat the key
        }
        if (isMain && isUp) {
            return true; // eat stray RAlt up
        }
    } else {
        if (isMain && isDown) {
            // v4: Emit toggle on the DOWN edge (keydown) instead of up (keyup).
            //
            // Rationale: the HookProc processes the down event ~0-5ms after
            // the physical press. The up event can be delayed by the user
            // holding the key much longer (100-500ms). By emitting on down,
            // we give the RAltStopWatcher (which also detects the down-edge)
            // a clear signal to compare against: if the hook fired, total_emitted
            // is already incremented before the watcher's grace window expires.
            // This eliminates the race where watcher fired on down before the
            // hook's up-edge emit.
            //
            // Auto-repeat keydown while held: the first down already set
            // g_matched=true, so subsequent downs (auto-repeat) enter the
            // else (g_matched==true) branch. We only emit once per match
            // cycle — guard with a flag that tracks whether we've already
            // emitted for this press.
            if (!g_emitted_this_press) {
                g_emitted_this_press = true;
                EmitToggle();
                if (allowSideEffects) {
                    ForceReleaseAlt();
                }
            }
            return true;
        }
        if (isMain && isUp) {
            // v4: UP only clears state and swallows. No EmitToggle — that
            // already happened on the down edge.
            g_matched = false;
            g_emitted_this_press = false;
            if (allowSideEffects) {
                ForceReleaseAlt();
            }
            return true;
        }
    }

    return false;
}

// ── Hook procedure (called on the hook thread) ──────────────────────
//
// Thin wrapper over HandleKeyEventCore. Records a native diagnostics entry
// before and after the state-machine parse so we can distinguish "event
// never reached HookProc" from "event reached but not matched".
//
static LRESULT CALLBACK HookProc(int nCode, WPARAM wParam, LPARAM lParam) {
    if (nCode < 0)
        return CallNextHookEx(nullptr, nCode, wParam, lParam);
    KBDLLHOOKSTRUCT& kbd = *reinterpret_cast<KBDLLHOOKSTRUCT*>(lParam);

    uint32_t mb = g_matched ? 1 : 0;

    bool eaten = HandleKeyEventCore(static_cast<UINT>(kbd.vkCode), wParam, kbd.flags, true);

    uint32_t ma = g_matched ? 1 : 0;
    // v4: emit happens on the down-edge (unmatched→matched transition with down event)
    uint32_t emitted = 0;
    if (mb == 0 && ma == 1 && (wParam == WM_KEYDOWN || wParam == WM_SYSKEYDOWN) &&
        (kbd.vkCode == VK_RMENU ||
         (kbd.vkCode == VK_MENU && (kbd.flags & LLKHF_EXTENDED)))) {
        emitted = 1;
    }

    RecordNativeEvent(static_cast<UINT>(kbd.vkCode), wParam, kbd.flags,
                      mb, ma, emitted);

    if (eaten)
        return 1;
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
    g_emitted_this_press = false;
    g_callback = reinterpret_cast<void(*)()>(callback_ptr);
    g_pending.store(0);
    g_total_emitted.store(0);
    g_total_consumed.store(0);

    // Reset native diagnostics ring
    g_native_seq = 0;
    g_native_write = 0;

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

// ── Native diagnostics exports ──────────────────────────────────────

__declspec(dllexport) unsigned long native_event_count(void) {
    // Total events recorded since install (== g_native_seq).
    // Safe to read without lock — only HookProc writes (serialized by hook
    // thread), and we only need a consistent-ish snapshot for diagnostics.
    return g_native_seq;
}

// Copy up to `max_entries` NativeEventRecord structs from the ring into
// the caller's buffer, starting from the oldest entry, in seq order.
// Returns the number of entries actually copied.
//
// Calling convention: the Python side allocates a buffer of
// `max_entries * sizeof(NativeEventRecord)` bytes and passes a pointer.
// This is safe because NativeEventRecord is a plain-old-data struct with
// no pointers; copying it is a shallow memcpy of integer fields only.
__declspec(dllexport) unsigned long native_events(
        NativeEventRecord* out_buffer, unsigned long max_entries) {
    if (!out_buffer || max_entries == 0) return 0;

    uint32_t total = g_native_seq;         // total written since install
    uint32_t write = g_native_write;       // current write position (mod ring)
    uint32_t available = (total < NATIVE_DIAG_RING_SIZE) ? total : NATIVE_DIAG_RING_SIZE;
    uint32_t to_copy = (static_cast<uint32_t>(max_entries) < available)
                       ? static_cast<uint32_t>(max_entries) : available;
    if (to_copy == 0) return 0;

    // The ring wraps: oldest entry is at (write - available) mod ring size.
    uint32_t start_slot = (write + NATIVE_DIAG_RING_SIZE - available) % NATIVE_DIAG_RING_SIZE;

    for (uint32_t i = 0; i < to_copy; i++) {
        uint32_t slot = (start_slot + i) % NATIVE_DIAG_RING_SIZE;
        out_buffer[i] = g_native_ring[slot];
    }
    return static_cast<unsigned long>(to_copy);
}

// ── Test-only entry point ───────────────────────────────────────────
//
// Simulates an emit from the HookProc WITHOUT a physical key, so the
// transport from native producer -> worker thread -> Python callback can
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

// ── Test-only HookProc-equivalent event injector ────────────────────
//
// Drives the EXACT parsing path used in production (HandleKeyEventCore)
// with arbitrary (vkCode, message, flags) tuples — i.e. the same data
// fields Windows fills into KBDLLHOOKSTRUCT for a real physical key.
// Returns 1 if the parser would have eaten the key, 0 if it would have
// passed through. Used by tests/test_keyboard_helper_physical.py to
// cover the real RAlt down->up state machine that the existing transport
// stress test bypasses.
//
// `allowSideEffects` is forced to false: we MUST NOT inject real keys
// into the OS from inside a unit test. Everything else (g_matched,
// EmitToggle, g_pending) behaves identically to HookProc.
//
__declspec(dllexport) int __test_handle_event(
        unsigned int vkCode, unsigned int wParam, unsigned int flags) {
    if (!g_running.load()) {
        return -1;
    }
    uint32_t mb = g_matched ? 1 : 0;
    bool eaten = HandleKeyEventCore(
        static_cast<UINT>(vkCode),
        static_cast<WPARAM>(wParam),
        static_cast<DWORD>(flags),
        false);
    uint32_t ma = g_matched ? 1 : 0;
    // Record native diagnostics for the test event too (helps verify the
    // ring in unit tests). Determine emitted based on state flip.
    // v4: emit happens on unmatched→matched transition with down event.
    uint32_t emitted = 0;
    if (mb == 0 && ma == 1 && (static_cast<UINT>(wParam) == WM_KEYDOWN ||
        static_cast<UINT>(wParam) == WM_SYSKEYDOWN) &&
        (static_cast<UINT>(vkCode) == VK_RMENU ||
         (static_cast<UINT>(vkCode) == VK_MENU && (flags & LLKHF_EXTENDED)))) {
        emitted = 1;
    }
    RecordNativeEvent(static_cast<UINT>(vkCode), static_cast<WPARAM>(wParam),
                      static_cast<DWORD>(flags), mb, ma, emitted);
    return eaten ? 1 : 0;
}

// ── Test-only state reset for the HookProc parser ───────────────────
//
// Lets a test reset `g_matched` between scenarios without uninstalling /
// reinstalling the hook (which is expensive and changes thread identity).
__declspec(dllexport) void __test_reset_state(void) {
    g_matched = false;
    g_emitted_this_press = false;
}

// ── ABI version / build identity ────────────────────────────────────
//
// Exposes the build identity of THIS DLL so the Python host can log it
// at startup. The version integer is a monotonically increasing tag
// bumped whenever the DLL's ABI changes (new exports, new behavior).
// Older builds that lack this export are detected by getattr() failing
// on the Python side.
//
// Version log:
//   1  initial v2 transport (worker thread + event)
//   2  + __test_handle_event / __test_reset_state, RAlt state machine
//        coverage hooks (2026-06-26)
//   3  + native diagnostics ring (NativeEventRecord, native_event_count,
//        native_events exports); HookProc records before/after each event
//        (2026-06-26-v3)
//   4  + emit on DOWN edge (keydown) instead of UP edge (keyup);
//        g_emitted_this_press flag prevents double-emit on auto-repeat;
//        HookProc emit detection updated for down-edge
//        (2026-06-28-v4)
#define SAYIT_KEYBOARD_HELPER_VERSION 4
#define SAYIT_KEYBOARD_HELPER_BUILD   "2026-06-28-v4"

__declspec(dllexport) unsigned int helper_version(void) {
    return SAYIT_KEYBOARD_HELPER_VERSION;
}

__declspec(dllexport) const char* helper_build_id(void) {
    return SAYIT_KEYBOARD_HELPER_BUILD;
}

#ifdef __cplusplus
}
#endif