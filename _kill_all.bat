@echo off
echo Killing Sayit processes... > D:\code\sayit_zcode\_kill_out.txt
wmic process where "name='electron.exe'" delete >> D:\code\sayit_zcode\_kill_out.txt 2>&1
wmic process where "CommandLine like '%%server.py%%' and name='python.exe'" delete >> D:\code\sayit_zcode\_kill_out.txt 2>&1
timeout /t 4 /nobreak >nul
echo --- remaining --- >> D:\code\sayit_zcode\_kill_out.txt
tasklist /FI "IMAGENAME eq electron.exe" /FO CSV /NH >> D:\code\sayit_zcode\_kill_out.txt 2>&1
tasklist /FI "IMAGENAME eq python.exe" /FO CSV /NH >> D:\code\sayit_zcode\_kill_out.txt 2>&1
echo --- port 17890 --- >> D:\code\sayit_zcode\_kill_out.txt
netstat -ano | findstr 17890 >> D:\code\sayit_zcode\_kill_out.txt 2>&1
echo DONE >> D:\code\sayit_zcode\_kill_out.txt