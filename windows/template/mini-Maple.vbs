' mini-Maple starten zonder zwart venster. Optioneel argument: een .mw/.mpl-bestand.
Option Explicit
Dim fso, sh, dir, cmd, i
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
If Not fso.FileExists(dir & "\runtime\python.exe") Then
  MsgBox "runtime\python.exe niet gevonden." & vbCrLf & "Pak eerst de volledige zip uit (niet starten vanuit de zip).", vbExclamation, "mini-Maple"
  WScript.Quit 1
End If
cmd = """" & dir & "\runtime\python.exe"" """ & dir & "\app\launcher.py"""
For i = 0 To WScript.Arguments.Count - 1
  cmd = cmd & " """ & WScript.Arguments(i) & """"
Next
sh.CurrentDirectory = dir
sh.Run cmd, 0, False
