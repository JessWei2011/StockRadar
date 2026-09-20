Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinTopMost {
    [DllImport("user32.dll")]
    public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
}
"@

# Retry for a few seconds to lock the window into HWND_TOPMOST (-1)
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Milliseconds 300
    $procs = Get-Process msedge, chrome, edge -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like "*StockRadar*" }
    $pinned = $false
    foreach ($p in $procs) {
        if ($p.MainWindowHandle -ne [IntPtr]::Zero) {
            # -1 = HWND_TOPMOST, 0x0043 = SWP_SHOWWINDOW | SWP_NOMOVE | SWP_NOSIZE
            [WinTopMost]::SetWindowPos($p.MainWindowHandle, [IntPtr](-1), 0, 0, 0, 0, 0x0043) | Out-Null
            $pinned = $true
        }
    }
    if ($pinned) { break }
}