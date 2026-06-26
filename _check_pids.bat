@echo off
tasklist /FI "PID eq 2496" /FO CSV /NH
tasklist /FI "PID eq 38564" /FO CSV /NH
tasklist /FI "IMAGENAME eq electron.exe" /FO CSV /NH
tasklist /FI "IMAGENAME eq python.exe" /FO CSV /NH
echo DONE