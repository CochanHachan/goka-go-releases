Set WshShell = CreateObject("WScript.Shell")
strDir = Replace(WScript.ScriptFullName, WScript.ScriptName, "")
WshShell.CurrentDirectory = strDir
WshShell.Run "pythonw """ & strDir & "igo_admin.py""", 0, False
