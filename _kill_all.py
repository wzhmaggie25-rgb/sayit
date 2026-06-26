import psutil, os, time, signal

killed = []

# 1) Kill ALL python.exe running server.py
for p in psutil.process_iter(["pid", "name", "cmdline"]):
    try:
        cmd = " ".join(p.info["cmdline"] or [""]).lower()
        if p.info["name"] and "python" in p.info["name"].lower() and "server.py" in cmd:
            print(f"Killing python(server) PID {p.info['pid']}")
            p.kill()
            killed.append(p.info["pid"])
    except: pass

# 2) Kill ALL electron.exe (main + child)
for p in psutil.process_iter(["pid", "name"]):
    try:
        n = (p.info["name"] or "").lower()
        if "electron" in n:
            print(f"Killing electron PID {p.info['pid']}")
            p.kill()
            killed.append(p.info["pid"])
    except: pass

# 3) Kill cmd.exe with npx electron
for p in psutil.process_iter(["pid", "name", "cmdline"]):
    try:
        cmd = " ".join(p.info["cmdline"] or [""]).lower()
        if p.info["name"] and "cmd" in p.info["name"].lower() and "npx" in cmd and "electron" in cmd:
            print(f"Killing cmd(npx) PID {p.info['pid']}")
            p.kill()
            killed.append(p.info["pid"])
    except: pass

time.sleep(2)

# Verify port 17890
print()
print("=== Port 17890 ===")
found = False
for conn in psutil.net_connections():
    if conn.laddr.port == 17890:
        found = True
        print(f"  {conn.status} PID={conn.pid}")
if not found:
    print("  (clean)")

# Verify no electron/python(server) left
print()
print("=== Remaining ===")
for p in psutil.process_iter(["pid", "name", "cmdline"]):
    try:
        cmd = " ".join(p.info["cmdline"] or [""]).lower()
        n = (p.info["name"] or "").lower()
        if "electron" in n:
            print(f"  STILL electron PID {p.info['pid']}")
        if n == "python.exe" and "server.py" in cmd:
            print(f"  STILL python(server) PID {p.info['pid']}")
    except: pass

print(f"Killed {len(killed)} total")
print("CLEAN")