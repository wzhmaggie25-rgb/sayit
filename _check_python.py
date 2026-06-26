import os, subprocess

candidates = [
    r"C:\Users\46136\AppData\Local\Programs\Python\Python312\python.exe",
    r"C:\Users\46136\AppData\Local\Microsoft\WindowsApps\python.exe",
    "python",
    "python3",
]
for c in candidates:
    is_path = "\\" in c
    exists = os.path.exists(c) if is_path else True
    print(f"{c}")
    print(f"  Exists: {exists}")
    if exists:
        try:
            r = subprocess.run([c, "--version"], capture_output=True, text=True, timeout=5)
            print(f"  Version: {r.stdout.strip() or r.stderr.strip()}")
        except Exception as e:
            print(f"  Error: {e}")
    print()

uv = r"C:\Users\46136\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\python.exe"
print(f"uv python: {uv}")
print(f"  Exists: {os.path.exists(uv)}")