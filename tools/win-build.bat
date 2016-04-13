FOR /F "TOKENS=1 eol=/ DELIMS=/ " %%A IN ('DATE/T') DO SET yyyy=%%A
FOR /F "TOKENS=1,2 eol=/ DELIMS=/ " %%A IN ('DATE/T') DO SET mm=%%B
FOR /F "TOKENS=1,2,3 eol=/ DELIMS=/ " %%A IN ('DATE/T') DO SET dd=%%C
SET TODAY=%yyyy%%mm%%dd%
echo %TODAY%
reg Query "HKLM\Hardware\Description\System\CentralProcessor\0" | find /i "x86" > NUL && set VERSION=x86|| set VERSION=x64
cd C:\Dev\fluxclient
python setup.py install
cd C:\Dev\fluxghost
rm -r C:\Dev\fluxghost\build
rm -rf C:\Dev\fluxghost\dist
pyinstaller ghost.spec
cp -r C:/Dev/win-dll-%VERSION%/* C:\Dev\fluxghost\dist\flux_api
mkdir dist\fluxghost-win-latest-%VERSION%
mv dist\flux_api dist\fluxghost-win-latest-%VERSION%\flux_api
cd dist
winrar a -afzip -r C:\Dev\fluxghost-win-latest-%VERSION%.zip fluxghost-win-latest-%VERSION% > ../rar_log
cd C:\Dev\fluxghost
dist\fluxghost-win-latest-%VERSION%\flux_api\flux_api.exe --assets=C:\Dev\web-panel\public
