// WH_KEYBOARD_LL hook DLL for Sayit - RAlt toggle (Typeless architecture)
// Exports for ctypes: install_hook(callback_ptr), uninstall_hook(), is_hook_installed()
// Compiled as a standalone DLL (no N-API dependency) so it works with any Python/Node version.

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
// KF_UP may already be defined in winuser.h on newer SDKs
#ifndef KF_UP
#define KF_UP       0x0002
#endif

// ── Hook state (process-global singleton) ───────────────────────────
static HHOOK                g_hHook = nullptr;
static std::thread          g_hookThread;
static DWORD                g_hookThreadId = 0;
static std::atomic<bool>    g_running{false};
static bool                 g_matched = false;

// Callback function pointer (set by install_hook)
// Called on the hook thread when RAlt is pressed and released (toggle event).
// Typeless architecture: callback is a simple void(*)() — lightweight, no marshalling.
static void                 (*g_callback)(void) = nullptr;

// Debug logging to DebugView (use DbgView from Sysinternals)
static void D(const char* msg) {
    OutputDebugStringA("[keyboard-helper] ");
    OutputDebugStringA(msg);
    OutputDebugStringA("\n");
}

// ── Win32 helpers ───────────────────────────────────────────────────

static void ForceReleaseAlt() {
    // Unconditionally release all three Alt VKs.  GetAsyncKeyState guard
    // is unreliable here because the WH_KEYBOARD_LL hook callback runs on
    // the hook thread — SendInput keyups injected from this context may
    // not immediately update GetAsyncKeyState on the same thread, causing
    // the guard to see "still pressed" and skip the release.
    //
    // Worse: VK_LMENU / VK_MENU stuck "pressed" makes every keystroke
    // Alt+key (menu accelerator) — keyboard goes dead.
    //
    // With the cancel-match path removed, ForceReleaseAlt is called at
    // most once per RAlt release, so the cost is negligible.
    UINT vks[] = {VK_RMENU, VK_LMENU, VK_MENU};
    for (int i = 0; i < 3; i++) {
        INPUT inp = {};
        inp.type = INPUT_KEYBOARD;
        inp.ki.wVk = static_cast<WORD>(vks[i]);
        inp.ki.dwFlags = KEYEVENTF_KEYUP;
        SendInput(1, &inp, sizeof(INPUT));
    }
}

// ── Hook procedure (called on the hook thread) ──────────────────────

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
            D("IDLE -> MATCHED: RAlt down");
            // Preemptive release: when the hook eats RAlt, the keyboard driver may have
            // already set VK_MENU / VK_LMENU async state for the same physical press,
            // depending on keyboard layout or scan-code mapping.  Release them now so
            // they don't remain stuck for the entire recording session.
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
            D("IDLE: eating stray RAlt up");
            return 1; // eat stray RAlt up
        }
    } else {
        // MATCHED state: wait for RAlt up
        if (isMain && isUp) {
            g_matched = false;
            D("MATCHED -> IDLE: RAlt up -> callback");
            // Call the registered callback (simple function pointer — no marshalling needed)
            if (g_callback) {
                g_callback();
            } else {
                D("ERROR: no callback registered");
            }
            ForceReleaseAlt();
            return 1; // eat the key
        }
        if (isMain && isDown) {
            D("MATCHED: eating repeat RAlt down");
            return 1; // eat repeat RAlt down
        }
        // NOTE: No "cancel match on other key" path.
        // Typeless architecture: during recording (RAlt held), user types freely.
        // Forcing Alt release per keystroke floods the input queue with synthetic
        // Alt-up events, confusing the Alt state machine and triggering menu focus.
    }

    return CallNextHookEx(nullptr, nCode, wParam, lParam);
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
    while (g_running && GetMessage(&msg, nullptr, 0, 0) > 0) {
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

// Install the WH_KEYBOARD_LL hook. callback_ptr is a void(*)() function pointer.
// Returns 1 on success, 0 on failure.
__declspec(dllexport) int install_hook(void* callback_ptr) {
    if (callback_ptr == nullptr) {
        D("install_hook: callback_ptr is null");
        return 0;
    }

    if (g_running) {
        D("install_hook: already running");
        return 0;
    }

    g_matched = false;
    g_callback = reinterpret_cast<void(*)()>(callback_ptr);
    g_running = true;

    g_hookThread = std::thread(HookThread);
    g_hookThread.detach();

    // Wait up to 500ms for hook to install
    for (int i = 0; i < 50; i++) {
        if (g_hHook) break;
        Sleep(10);
    }

    D(g_hHook ? "install_hook: OK" : "install_hook: FAILED");
    return (g_hHook != nullptr) ? 1 : 0;
}

// Uninstall the hook. Returns 1 on success.
__declspec(dllexport) int uninstall_hook(void) {
    D("uninstall_hook: stopping hook");

    g_running = false;
    g_callback = nullptr;

    // Wake the hook thread from GetMessage so it can exit
    DWORD tid = g_hookThreadId;
    if (tid != 0) {
        PostThreadMessage(tid, WM_QUIT, 0, 0);
    }

    return 1;
}

// Check if the hook is currently installed. Returns 1 if installed, 0 otherwise.
__declspec(dllexport) int is_hook_installed(void) {
    return (g_running && g_hHook != nullptr) ? 1 : 0;
}

#ifdef __cplusplus
}
#endif