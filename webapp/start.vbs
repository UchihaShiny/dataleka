' Bat backend dashboard DataE an (khong hien cua so), cho http://127.0.0.1:8600
' Dat loi tat toi file nay trong thu muc Startup (Win+R, go shell:startup) de tu bat khi dang nhap Windows.
' Log: logs\webapp.log. Tat: chay webapp\stop.bat. Da chay roi thi lan bat thu 2 tu thoat (cong 8600 dang dung).
' Chi viet chu khong dau: wscript doc file theo bang ma cu.
Dim fso, shell, root
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
shell.CurrentDirectory = root
If Not fso.FolderExists(root & "\logs") Then fso.CreateFolder(root & "\logs")
shell.Run "cmd /c set PYTHONIOENCODING=utf-8&& python -m uvicorn webapp.api.main:app --host 127.0.0.1 --port 8600 >> logs\webapp.log 2>&1", 0, False
