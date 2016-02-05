cd C:\Dev
reg Query "HKLM\Hardware\Description\System\CentralProcessor\0" | find /i "x86" > NUL && set VERSION=x86|| set VERSION=x64
scp ./fluxghost-win-latest-%VERSION%.zip simon@192.168.16.202:/var/www/latest-release/ghost/windows/fluxghost-win-latest-%VERSION%.zip