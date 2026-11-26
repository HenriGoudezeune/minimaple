' Verwijdert de koppeling van .mw/.mpl met mini-Maple (enkel jouw gebruiker).
Option Explicit
Dim sh, ext
Set sh = CreateObject("WScript.Shell")
On Error Resume Next
For Each ext In Array(".mw", ".mpl")
  sh.RegDelete "HKCU\Software\Classes\" & ext & "\OpenWithProgids\miniMaple.Werkblad"
  sh.RegDelete "HKCU\Software\Classes\" & ext & "\OpenWithProgids\"
  If sh.RegRead("HKCU\Software\Classes\" & ext & "\") = "miniMaple.Werkblad" Then sh.RegDelete "HKCU\Software\Classes\" & ext & "\"
Next
sh.RegDelete "HKCU\Software\Classes\miniMaple.Werkblad\shell\open\command\"
sh.RegDelete "HKCU\Software\Classes\miniMaple.Werkblad\shell\open\"
sh.RegDelete "HKCU\Software\Classes\miniMaple.Werkblad\shell\"
sh.RegDelete "HKCU\Software\Classes\miniMaple.Werkblad\DefaultIcon\"
sh.RegDelete "HKCU\Software\Classes\miniMaple.Werkblad\"
sh.RegDelete "HKCU\Software\RegisteredApplications\mini-Maple"
sh.RegDelete "HKCU\Software\miniMaple\Capabilities\FileAssociations\"
sh.RegDelete "HKCU\Software\miniMaple\Capabilities\"
sh.RegDelete "HKCU\Software\miniMaple\"
sh.RegDelete "HKCU\Software\Classes\minimaple\shell\open\command\"
sh.RegDelete "HKCU\Software\Classes\minimaple\shell\open\"
sh.RegDelete "HKCU\Software\Classes\minimaple\shell\"
sh.RegDelete "HKCU\Software\Classes\minimaple\"
MsgBox "Bestandskoppeling verwijderd.", vbInformation, "mini-Maple"
