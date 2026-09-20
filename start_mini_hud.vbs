Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
WshShell.CurrentDirectory = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.Environment("PROCESS")("PYTHONPATH") = WshShell.CurrentDirectory & "\src;" & WshShell.CurrentDirectory & "\.deps"
WshShell.Environment("PROCESS")("PYTHONIOENCODING") = "utf-8"

' Ensure full background engine (Web Server + Shioaji Live Collector) is running silently
WshShell.Run "pythonw -m stock_radar.launcher --no-browser --start-monitoring", 0, False
WScript.Sleep 600

' Launch lightweight App Mode window as vertical right-dock sidebar with tall pillar lamps
Dim edgePath
edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
If Not FSO.FileExists(edgePath) Then
    edgePath = "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
End If

If FSO.FileExists(edgePath) Then
    WshShell.Run """" & edgePath & """ --app=http://127.0.0.1:8765/web/mini.html --window-size=220,680 --window-position=1690,40", 1, False
Else
    WshShell.Run "cmd /c start http://127.0.0.1:8765/web/mini.html", 0, False
End If

' Automatically lock window to Always-On-Top (HWND_TOPMOST)
WshShell.Run "powershell -ExecutionPolicy Bypass -NoProfile -File """ & WshShell.CurrentDirectory & "\pin_topmost.ps1""", 0, False