import subprocess, os, time

# Simulate what Electron does
server_py = os.path.join(os.path.dirname(__file__), "server.py")
python = r"C:\Users\46136\AppData\Local\Programs\Python\Python312\python.exe"

print(f"Testing: {python} {server_py}")
print(f"CWD: {os.path.dirname(__file__)}")
result = subprocess.run(
    [python, server_py],
    cwd=os.path.dirname(__file__),
    capture_output=True,
    text=True,
    timeout=8
)
print("STDOUT:", result.stdout[-2000:] if result.stdout else "(none)")
print("STDERR:", result.stderr[-2000:] if result.stderr else "(none)")
print("RC:", result.returncode)