' Optioneel: .mw- en .mpl-bestanden openen met mini-Maple (enkel voor jouw gebruiker, geen admin nodig).
' Ongedaan maken: bestandskoppeling-uit.vbs
Option Explicit
Dim fso, sh, dir, k, ext
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
If MsgBox(".mw- en .mpl-bestanden voortaan openen met mini-Maple?" & vbCrLf & _
  "(Heb je echte Maple, dan neemt mini-Maple die koppeling over voor jouw gebruiker.)", _
  vbYesNo + vbQuestion, "mini-Maple") <> vbYes Then WScript.Quit 0
k = "HKCU\Software\Classes\miniMaple.Werkblad\"
sh.RegWrite k, "mini-Maple-werkblad", "REG_SZ"
sh.RegWrite k & "DefaultIcon\", dir & "\app\mini-Maple.ico,0", "REG_SZ"
sh.RegWrite k & "shell\open\command\", """" & sh.ExpandEnvironmentStrings("%SystemRoot%") & _
  "\System32\wscript.exe"" """ & dir & "\mini-Maple.vbs"" ""%1""", "REG_SZ"
For Each ext In Array(".mw", ".mpl")
  sh.RegWrite "HKCU\Software\Classes\" & ext & "\", "miniMaple.Werkblad", "REG_SZ"
  sh.RegWrite "HKCU\Software\Classes\" & ext & "\OpenWithProgids\miniMaple.Werkblad", "", "REG_SZ"
Next
' Zichtbaar maken in Instellingen > Apps > Standaard-apps
Dim c : c = "HKCU\Software\miniMaple\Capabilities\"
sh.RegWrite c & "ApplicationName", "mini-Maple", "REG_SZ"
sh.RegWrite c & "ApplicationDescription", "Rekenomgeving met Maple-syntax", "REG_SZ"
sh.RegWrite c & "FileAssociations\.mw", "miniMaple.Werkblad", "REG_SZ"
sh.RegWrite c & "FileAssociations\.mpl", "miniMaple.Werkblad", "REG_SZ"
sh.RegWrite "HKCU\Software\RegisteredApplications\mini-Maple", "Software\miniMaple\Capabilities", "REG_SZ"
MsgBox "Klaar. Windows vraagt soms nog één keer: rechtsklik een .mw-bestand > Openen met > mini-Maple > 'Altijd'." & vbCrLf & _
  "Of: Instellingen > Apps > Standaard-apps > mini-Maple.", vbInformation, "mini-Maple"
