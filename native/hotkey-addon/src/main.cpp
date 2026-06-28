// WH_KEYBOARD_LL hook addon for Sayit - RAlt toggle (Typeless architecture)
#include <napi.h>
#include <windows.h>
#include <thread>
#include <atomic>
#include <mutex>

// Undefine conflicting macros from winuser.h before redefining
#undef KF_UP

// VK constants (macros for MSVC compatibility)
#define VK_MASK     0xE8
#define VK_RMENU    0xA5
#define VK_LMENU    0xA4
#define VK_MENU     0x12
#define LL_HOOK     13
#define KF_UP       0x0002

// Debug logging to DebugView (use DbgView from sysinternals to see output)
static void D(const char* msg) {
    OutputDebugStringA("[hotkey-addon] ");
    OutputDebugStringA(msg);
    OutputDebugStringA("\n");
}

// Hook state (process-global singleton)
static HHOOK                     g_hHook = nullptr;
static std::thread               g_hookThread;
static DWORD                     g_hookThreadId = 0;
static std::atomic<bool>         g_running{false};
static std::mutex                g_mutex;
static Napi::ThreadSafeFunction  g_tsfn;
static std::atomic<bool>         g_tsfnValid{false};
static bool                      g_matched = false;

// Win32 helpers
static void SendMaskKey() {
    keybd_event(VK_MASK, 0, 0, 0);
    keybd_event(VK_MASK, 0, KF_UP, 0);
}

static void ConditionalReleaseAlt() {
    UINT vks[] = {VK_RMENU, VK_LMENU, VK_MENU};
    for (int i = 0; i < 3; i++) {
        if (!(GetAsyncKeyState(vks[i]) & 0x8000))
            continue;
        keybd_event(vks[i], 0, KF_UP, 0);
    }
    SendMaskKey();
}

// Hook procedure (called on hook thread)
static LRESULT CALLBACK HookProc(int nCode, WPARAM wParam, LPARAM lParam) {
    if (nCode < 0)
        return CallNextHookEx(nullptr, nCode, wParam, lParam);

    KBDLLHOOKSTRUCT& kbd = *reinterpret_cast<KBDLLHOOKSTRUCT*>(lParam);
    UINT vk = static_cast<UINT>(kbd.vkCode);
    DWORD flags = kbd.flags;

    if (flags & LLKHF_INJECTED)
        return CallNextHookEx(nullptr, nCode, wParam, lParam);

    bool isDown = (wParam == WM_KEYDOWN || wParam == WM_SYSKEYDOWN);
    bool isUp   = (wParam == WM_KEYUP   || wParam == WM_SYSKEYUP);
    bool isMain = (vk == VK_RMENU || vk == VK_MENU);

    // Normalize VK_MENU (0x12) to left/right based on LLKHF_EXTENDED
    if (vk == VK_MENU) {
        vk = (flags & LLKHF_EXTENDED) ? VK_RMENU : VK_LMENU;
        isMain = (vk == VK_RMENU);
    }

    if (!g_matched) {
        // IDLE state: wait for RAlt down
        if (isMain && isDown) {
            g_matched = true;
            D("IDLE → MATCHED: RAlt down");
            SendMaskKey();
            return 1; // eat the key
        }
        if (isMain && isUp) {
            D("IDLE: eating stray RAlt up");
            return 1; // eat stray RAlt up
        }
    } else {
        // MATCHED state: wait for RAlt up
        if (isMain && isUp) {
            g_matched = false;
            D("MATCHED → IDLE: RAlt up → BlockingCall");
            // Notify JS via ThreadSafeFunction (no data needed)
            if (g_tsfnValid.load()) {
                g_tsfn.BlockingCall();
            } else {
                D("ERROR: TSFn not valid on BlockingCall!");
            }
            ConditionalReleaseAlt();
            return 1; // eat the key
        }
        if (isMain && isDown) {
            D("MATCHED: eating repeat RAlt down");
            return 1; // eat repeat RAlt down
        }
        if (isDown) {
            D("MATCHED: other key pressed, cancel match");
            // Another key pressed while RAlt held => cancel match
            g_matched = false;
            ConditionalReleaseAlt();
        }
    }

    return CallNextHookEx(nullptr, nCode, wParam, lParam);
}

// Hook thread: owns the hook and message pump
static void HookThread() {
    g_hookThreadId = GetCurrentThreadId();

    g_hHook = SetWindowsHookEx(WH_KEYBOARD_LL, HookProc, GetModuleHandle(nullptr), 0);
    if (!g_hHook) {
        g_running = false;
        return;
    }

    MSG msg;
    while (g_running && GetMessage(&msg, nullptr, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }

    if (g_hHook) {
        UnhookWindowsHookEx(g_hHook);
        g_hHook = nullptr;
    }
    g_matched = false;
    g_hookThreadId = 0;
}

// Napi bindings
Napi::Value Install(const Napi::CallbackInfo& info) {
    Napi::Env env = info.Env();
    if (info.Length() < 1 || !info[0].IsFunction()) {
        Napi::TypeError::New(env, "callback required").ThrowAsJavaScriptException();
        return env.Undefined();
    }

    std::lock_guard<std::mutex> lock(g_mutex);

    if (g_running) {
        D("Install: already running");
        return Napi::Boolean::New(env, false);
    }

    g_matched = false;
    g_running = true;

    Napi::Function cb = info[0].As<Napi::Function>();
    // CRITICAL: initialThreadCount = 0 + manual Acquire() to prevent premature
    // closing of the ThreadSafeFunction after a single BlockingCall.
    // This is the standard pattern for long-lived TSFns called from background threads.
    g_tsfn = Napi::ThreadSafeFunction::New(
        env, cb, "tsfn", 0, 0
    );
    g_tsfn.Acquire();          // ref = 1 — keep alive until manual Release()
    g_tsfn.Unref(env);         // Don't prevent Node event loop from exiting
    g_tsfnValid.store(true);
    D("Install: TSFn created (ref=1, unref'd)");

    g_hookThread = std::thread(HookThread);
    g_hookThread.detach();

    // Wait up to 500ms for hook to install
    for (int i = 0; i < 50; i++) {
        if (g_hHook) break;
        Sleep(10);
    }

    D(g_hHook ? "Install: hook OK" : "Install: hook FAILED");
    return Napi::Boolean::New(env, g_hHook != nullptr);
}

Napi::Value Uninstall(const Napi::CallbackInfo& info) {
    Napi::Env env = info.Env();

    std::lock_guard<std::mutex> lock(g_mutex);

    g_running = false;
    D("Uninstall: stopping hook");

    // Wake the hook thread from GetMessage so it can exit
    DWORD tid = g_hookThreadId;
    if (tid != 0) {
        PostThreadMessage(tid, WM_QUIT, 0, 0);
    }

    // Release the ThreadSafeFunction
    if (g_tsfnValid.load()) {
        g_tsfn.Release();      // ref from Acquire() → 0, TSFn closes
        g_tsfnValid.store(false);
        D("Uninstall: TSFn released");
    }

    return env.Undefined();
}

Napi::Value IsInstalled(const Napi::CallbackInfo& info) {
    return Napi::Boolean::New(info.Env(), g_running && g_hHook != nullptr);
}

Napi::Object Init(Napi::Env env, Napi::Object exports) {
    exports.Set("install",     Napi::Function::New(env, Install));
    exports.Set("uninstall",   Napi::Function::New(env, Uninstall));
    exports.Set("isInstalled", Napi::Function::New(env, IsInstalled));
    return exports;
}

NODE_API_MODULE(hotkey_addon, Init)