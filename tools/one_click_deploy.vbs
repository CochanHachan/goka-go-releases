Set WshShell = CreateObject("WScript.Shell")
strDir = Replace(WScript.ScriptFullName, WScript.ScriptName, "")
WshShell.CurrentDirectory = strDir
WshShell.Run "pythonw """ & strDir & "one_click_deploy.py""", 1, False
