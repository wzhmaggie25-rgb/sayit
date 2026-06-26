"""Kill all Sayit-related processes and restart cleanly."""
import subprocess, time, os, signal

# Kill electron
subprocess.run(["taskkill", "/F", "/IM", "electron.exe"], capture_output=True)
# Kill python processes that are running server.py
result = subprocess.run(["wmic", "process", "where", "name='python.exe'", "get", "ProcessId,CommandLine"], 
                       capture_output=True, text=True)
pids_to_kill = []
for line in result.stdout.splitlines():
    if "server.py" in line or "sayit" in line.lower():
        parts = line.strip().split()
        for p in parts:
            if p.isdigit():
                pids_to_kill.append(p)
                break

for pid in pids_to_kill:
    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
    print(f"Killed PID {pid}")

time.sleep(3)

# Check port
result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
for line in result.stdout.splitlines():
    if "17890" in line:
        print(f"Port 17890: {line.strip()}")

print("Ready to restart")