Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.Environment("PROCESS")("PYTHONPATH") = WshShell.CurrentDirectory & "\src;" & WshShell.CurrentDirectory & "\.deps"
WshShell.Environment("PROCESS")("PYTHONIOENCODING") = "utf-8"
WshShell.Run "pythonw -m stock_radar.launcher", 0, False