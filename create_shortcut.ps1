$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$HOME\Desktop\Start Serwer RaportProdukcyjny.lnk")
$Shortcut.TargetPath = "c:\Users\Admin\Documents\GitHub\RaportProdukcyjny\Start_Serwer.bat"
$Shortcut.WorkingDirectory = "c:\Users\Admin\Documents\GitHub\RaportProdukcyjny"
$Shortcut.IconLocation = "cmd.exe"
$Shortcut.Save()
