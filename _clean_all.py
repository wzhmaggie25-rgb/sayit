import psutil, os, time

# Kill everything Sayit-related
killed = []
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        cmd = ' '.join(p.info['cmdline'] or ['']).lower()
        n = (p.info['name'] or '').lower()
        
        # cmd.exe with npx electron
        if n == 'cmd.exe' and 'npx' in cmd and 'electron' in cmd:
            p.kill()
            killed.append(f'cmd {p.info["pid"]} (npx electron)')
        
        # electron.exe
        if 'electron' in n:
            p.kill()
            killed.append(f'electron {p.info["pid"]}')
        
        # python.exe with server.py
        if n == 'python.exe' and 'server.py' in cmd:
            p.kill()
            killed.append(f'python {p.info["pid"]} (server.py)')
    except:
        pass

print(f'Killed {len(killed)} processes:')
for k in killed:
    print(f'  {k}')

time.sleep(2)

print()
print('=== Port 17890 ===')
for conn in psutil.net_connections():
    if conn.laddr.port == 17890:
        print(f'  {conn.status} PID={conn.pid}')

print('=== Electron processes remaining ===')
for p in psutil.process_iter(['pid', 'name']):
    n = (p.info['name'] or '').lower()
    if 'electron' in n:
        print(f'  STILL: PID {p.info["pid"]}')

print('Done - clean state')