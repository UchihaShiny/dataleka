@echo off
rem Tat backend dashboard DataE (tien trinh dang nghe cong 8600).
rem Chi viet chu khong dau: cmd doc file .bat theo bang ma cu, chu co dau lam hong lenh.
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 8600 -State Listen -ErrorAction SilentlyContinue; if (-not $c) { 'Backend khong chay.' } else { $c | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force; 'Da tat backend (PID ' + $_.OwningProcess + ').' } }"
