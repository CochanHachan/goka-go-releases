Set WshShell = CreateObject("WScript.Shell")
strDir = Replace(WScript.ScriptFullName, WScript.ScriptName, "")
WshShell.CurrentDirectory = strDir
WshShell.Run "pythonw """ & strDir & "merge_prs.py""", 1, False
