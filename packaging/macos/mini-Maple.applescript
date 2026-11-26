-- Dun AppleScript-applet: handelt Finder- en URL-events af (ook als mini-Maple al draait)
-- en start telkens de Python-launcher op de achtergrond. De launcher hergebruikt een lopende server.
on run
	launchMM("")
end run

on open theItems
	repeat with f in theItems
		launchMM(POSIX path of f)
	end repeat
end open

on open location theURL
	launchMM(theURL)
end open location

on launchMM(arg)
	set res to (POSIX path of (path to me)) & "Contents/Resources/"
	set cmd to quoted form of (res & "python/bin/python3") & " -s " & quoted form of (res & "app/launcher.py")
	if arg is not "" then set cmd to cmd & " " & quoted form of arg
	do shell script "PYTHONDONTWRITEBYTECODE=1 " & cmd & " >/dev/null 2>&1 &"
end launchMM
