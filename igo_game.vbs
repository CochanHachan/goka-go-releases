Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "pythonw """ & Replace(WScript.ScriptFullName, WScript.ScriptName, "") & "igo_game.py""", 0, False
