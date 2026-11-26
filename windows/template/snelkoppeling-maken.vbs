' Maakt een snelkoppeling "mini-Maple" op het bureaublad (en in het Startmenu).
Option Explicit
Dim fso, sh, dir, lnk, places, p
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
places = Array(sh.SpecialFolders("Desktop"), sh.SpecialFolders("Programs"))
For Each p In places
  Set lnk = sh.CreateShortcut(p & "\mini-Maple.lnk")
  lnk.TargetPath = sh.ExpandEnvironmentStrings("%SystemRoot%") & "\System32\wscript.exe"
  lnk.Arguments = """" & dir & "\mini-Maple.vbs"""
  lnk.WorkingDirectory = dir
  lnk.IconLocation = dir & "\app\mini-Maple.ico,0"
  lnk.Description = "mini-Maple (offline)"
  lnk.Save
Next
MsgBox "Snelkoppeling gemaakt op het bureaublad en in het Startmenu." & vbCrLf & _
  "Verplaats je deze map later, voer dit script dan opnieuw uit.", vbInformation, "mini-Maple"
