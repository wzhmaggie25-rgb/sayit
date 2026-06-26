"""Targeted Python/comtypes MTA + context_helper DLL apartment test.

Validates the COM apartment fix in ``native/context_helper/src/main.cpp``:
the DLL build must use ``COINIT_MULTITHREADED`` so that loading it on a
Python thread which has already been initialised as MTA (e.g. by
``comtypes.CoInitializeEx(COINIT_MULTITHREADED)`` or by the comtypes
default for non-Tk threads) does not trip ``RPC_E_CHANGED_MODE`` inside
the DLL's ``ComInit``.

IMPORTANT: pytest may initialise the main thread as STA (via anyio etc.).
This test detects that and runs the actual DLL load + UIA validation in a
*subprocess* to guarantee a fresh thread with explicit MTA init.

The subprocess launches notepad.exe, writes a unique sentinel into its edit
control via the Win32 message API (no SendInput; no clipboard), then calls
the DLL's ``get_full_context_json`` for the notepad HWND in the same Python
thread and asserts the UIA path actually returned the sentinel (or,
conservatively, a non-empty editable UIA payload).

Important: this is NOT a "JSON-parses" smoke test. The assertions require
evidence that the UIA path actually ran inside the DLL.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IS_WINDOWS = sys.platform == "win32"


def _dll_built() -> bool:
    candidates = [
        PROJECT_ROOT / "native" / "context_helper" / "build" / "Release" / "sayit_context_helper_dll.dll",
        PROJECT_ROOT / "native" / "context_helper" / "build" / "Debug" / "sayit_context_helper_dll.dll",
    ]
    return any(p.exists() for p in candidates)


def _run_dll_test_subprocess() -> dict:
    """Run DLL + COM + UIA validation in a fresh subprocess.

    Returns dict with keys: stdout, stderr, returncode, timed_out.
    """
    root = str(PROJECT_ROOT)
    dll_path = root + "\\native\\context_helper\\build\\Release\\sayit_context_helper_dll.dll"
    exe_path = root + "\\native\\context_helper\\build\\Release\\sayit_context_helper.exe"

    # The subprocess script that runs in a fresh interpreter (no prior COM init)
    script = (
        "import ctypes,ctypes.wintypes,json,os,subprocess,sys,time,uuid\n"
        "ole32=ctypes.windll.ole32\n"
        "COINIT_MULTITHREADED=0x0\n"
        "hr=ole32.CoInitializeEx(None,COINIT_MULTITHREADED)\n"
        "if hr&0xFFFFFFFF==0x80010106:\n"
        " print('SUB:SKIP|thread already STA');sys.exit(0)\n"
        f"dll=r'{dll_path}'\n"
        f"exe=r'{exe_path}'\n"
        "if not os.path.exists(dll):\n"
        " print('SUB:SKIP|DLL not found');sys.exit(0)\n"
        "# EXE ping regression\n"
        "r=subprocess.run([exe],input='{\"id\":\"0\",\"method\":\"ping\"}\\n',capture_output=True,text=True,timeout=10)\n"
        "ping=json.loads(r.stdout.strip())\n"
        "if not ping.get('ok'):\n"
        " print('SUB:FAIL|EXE ping '+str(ping));sys.exit(1)\n"
        "# EXE get_full_context\n"
        "r2=subprocess.run([exe],input='{\"id\":\"1\",\"method\":\"get_full_context\"}\\n',capture_output=True,text=True,timeout=10)\n"
        "ctx2=json.loads(r2.stdout.strip())\n"
        "if not ctx2.get('ok'):\n"
        " print('SUB:FAIL|EXE get_full_context');sys.exit(1)\n"
        "# Launch notepad\n"
        "windir=os.environ.get('WINDIR',r'C:\\Windows')\n"
        "notepad=windir+r'\\System32\\notepad.exe'\n"
        "if not os.path.exists(notepad):\n"
        " print('SUB:SKIP|notepad not found');sys.exit(0)\n"
        "proc=subprocess.Popen([notepad])\n"
        "time.sleep(1.0)\n"
        "user32=ctypes.windll.user32\n"
        "def find_hwnd(pid):\n"
        " found=[0]\n"
        " W=ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL,ctypes.wintypes.HWND,ctypes.wintypes.LPARAM)\n"
        " def cb(hwnd,_):\n"
        "  buf=ctypes.create_unicode_buffer(256)\n"
        "  user32.GetClassNameW(hwnd,buf,256)\n"
        "  po=ctypes.wintypes.DWORD(0)\n"
        "  user32.GetWindowThreadProcessId(hwnd,ctypes.byref(po))\n"
        "  if po.value==pid and user32.IsWindowVisible(hwnd):\n"
        "   found[0]=hwnd;return False\n"
        "  return True\n"
        " user32.EnumWindows(W(cb),0)\n"
        " return found[0]\n"
        "hwnd=find_hwnd(proc.pid)\n"
        "deadline=time.time()+8\n"
        "while not hwnd and time.time()<deadline:\n"
        " time.sleep(0.2);hwnd=find_hwnd(proc.pid)\n"
        "if not hwnd:\n"
        " proc.kill();proc.wait();print('SUB:SKIP|could not find notepad window');sys.exit(0)\n"
        "sentinel='sayit-com-'+uuid.uuid4().hex[:8]\n"
        "edit=user32.FindWindowExW(hwnd,0,'Edit',None)\n"
        "if not edit:\n"
        " edit=user32.FindWindowExW(hwnd,0,'RichEditD2DPT',None)\n"
        "if not edit:\n"
        " proc.kill();proc.wait();print('SUB:SKIP|no edit child');sys.exit(0)\n"
        "SW=user32.SendMessageW\n"
        "SW.argtypes=[ctypes.wintypes.HWND,ctypes.wintypes.UINT,ctypes.wintypes.WPARAM,ctypes.wintypes.LPCWSTR]\n"
        "SW.restype=ctypes.c_ssize_t\n"
        "SW(edit,0x000C,0,sentinel)\n"
        "time.sleep(0.5)\n"
        "# Load DLL\n"
        "lib=ctypes.CDLL(dll)\n"
        "lib.get_full_context_json.argtypes=[ctypes.c_void_p]\n"
        "lib.get_full_context_json.restype=ctypes.c_void_p\n"
        "lib.free_string.argtypes=[ctypes.c_void_p]\n"
        "lib.free_string.restype=None\n"
        "ptr=lib.get_full_context_json(ctypes.c_void_p(hwnd))\n"
        "if not ptr:\n"
        " proc.kill();proc.wait();ole32.CoUninitialize()\n"
        " print('SUB:FAIL|DLL returned NULL');sys.exit(1)\n"
        "raw=ctypes.string_at(ptr).decode('utf-8')\n"
        "lib.free_string(ptr)\n"
        "try:result=json.loads(raw)\n"
        "except Exception as e:\n"
        " proc.kill();proc.wait();ole32.CoUninitialize()\n"
        " print('SUB:FAIL|JSON '+str(e));sys.exit(1)\n"
        "proc.kill();proc.wait(timeout=3);ole32.CoUninitialize()\n"
        "tip=result.get('text_insertion_point',{})\n"
        "full=tip.get('cursor_state',{}).get('full_field_content','')\n"
        "caps=tip.get('input_capabilities',{}) or {}\n"
        "is_editable=bool(caps.get('is_editable'))\n"
        "role=tip.get('accessibility_role','')\n"
        "if sentinel in full:\n"
        " print('SUB:PASS|sentinel_found|'+repr(full[:80]))\n"
        "elif is_editable and (role or caps.get('dom_classes')):\n"
        " print('SUB:PASS|uia_metadata|role='+str(role)+'|editable='+str(is_editable))\n"
        "else:\n"
        " print('SUB:FAIL|no_uia|sentinel='+sentinel+'|full='+repr(full[:80])+'|role='+str(role))\n"
        " sys.exit(1)\n"
    )

    try:
        r = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {"stdout": r.stdout, "stderr": r.stderr, "returncode": r.returncode, "timed_out": False}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "", "returncode": -1, "timed_out": True}


@unittest.skipUnless(IS_WINDOWS, "Windows-only test")
class ContextHelperDllComApartmentTests(unittest.TestCase):
    """Validate the DLL COM apartment fix by running a focused subprocess test."""

    def test_dll_com_apartment_and_uia(self):
        """Run the DLL in a fresh subprocess with explicit MTA init, verify UIA works."""
        if not _dll_built():
            self.skipTest("sayit_context_helper_dll.dll not built — run build.ps1 first")

        result = _run_dll_test_subprocess()

        if result.get("timed_out"):
            self.fail("DLL test subprocess timed out (30s)")

        stdout = result["stdout"]

        # Check for skip
        if "SUB:SKIP|" in stdout:
            reason = stdout.split("SUB:SKIP|")[1].split("\n")[0].strip()
            self.skipTest(reason)

        # Check for pass
        if "SUB:PASS|" in stdout:
            return  # success

        # Check for explicit fail
        if "SUB:FAIL|" in stdout:
            detail = stdout.split("SUB:FAIL|")[1].split("\n")[0].strip()
            self.fail(f"DLL test failed: {detail}")

        if result["returncode"] != 0:
            self.fail(
                f"DLL subprocess exited {result['returncode']}:\n"
                f"STDOUT:{stdout[:500]}\nSTDERR:{result['stderr'][:200]}"
            )


if __name__ == "__main__":
    unittest.main()