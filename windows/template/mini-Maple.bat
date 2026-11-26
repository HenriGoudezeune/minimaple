@echo off
rem mini-Maple met zichtbaar consolevenster (handig bij problemen: foutmeldingen blijven zichtbaar).
"%~dp0runtime\python.exe" "%~dp0app\launcher.py" %*
if errorlevel 1 pause
