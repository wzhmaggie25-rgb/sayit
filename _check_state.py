import psutil, os, time

print("=== Processes ===")
for p in psutil.process_iter(["pid", "name", "cmdline"]):
    try:
        cmd = " ".join(p.info["cmdline"] or [""]).lower()
        n = (p.info["name"] or "").lower()
        if "electron" in n:
            print(f'Electron PID {p.info["pid"]}: {cmd[:120]}')
        if n == "python.exe" and "server.py" in cmd:
            print(f'Python(server) PID {p.info["pid"]}: {cmd[:120]}')
        if n == "cmd.exe" and "npx" in cmd and "electron" in cmd:
            print(f'CMD(npx) PID {p.info["pid"]}: {cmd[:80]}')
    except:
        pass

print()
print("=== Port 17890 ===")
for conn in psutil.net_connections():
    if conn.laddr.port == 17890:
        pname = "?"
        try: pname = psutil.Process(conn.pid).name()
        except: pass
        print(f'  {conn.status} PID={conn.pid} ({pname})')

print()
print("=== WS ESTABLISHED count ===")
ws_count = 0
for conn in psutil.net_connections():
    if conn.status == "ESTABLISHED" and conn.raddr and conn.raddr.port == 17890:
        ws_count += 1
        try:
            pn = psutil.Process(conn.pid).name()
        except:
            pn = "?"
        print(f'  {conn.laddr.port} -> 17890 (PID {conn.pid}/{pn})')
print(f'Total WS connections: {ws_count}')