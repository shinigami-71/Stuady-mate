Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

root = fso.GetParentFolderName(WScript.ScriptFullName)
pythonExe = root & "\.venv\Scripts\python.exe"
logFile = root & "\ai_backend\server.log"

If Not fso.FileExists(pythonExe) Then
    pythonExe = root & "\venv\Scripts\python.exe"
End If

command = "cmd /c cd /d """ & root & """ && """ & pythonExe & """ ai_backend\main.py --host 127.0.0.1 --port 8000 > """ & logFile & """ 2>&1"

shell.Run command, 0, False
