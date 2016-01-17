FOR /F "TOKENS=1 eol=/ DELIMS=/ " %%A IN ('DATE/T') DO SET yyyy=%%A
FOR /F "TOKENS=1,2 eol=/ DELIMS=/ " %%A IN ('DATE/T') DO SET mm=%%B
FOR /F "TOKENS=1,2,3 eol=/ DELIMS=/ " %%A IN ('DATE/T') DO SET dd=%%C
SET TODAY=%yyyy%%mm%%dd%
echo %TODAY%
SET VERSION=x64

cd C:\Dev\fluxclient
python setup.py install
cd C:\Dev\fluxghost
rm -r C:\Dev\fluxghost\build
rm -rf C:\Dev\fluxghost\dist
pyinstaller ghost.spec
cp -r C:/Dev/win-dll-%VERSION%/* C:\Dev\fluxghost\dist\ghost
mkdir dist\fluxghost-win-latest-x64
mv dist\ghost dist\fluxghost-win-latest-x64\ghost
cd dist
winrar a -afzip -r C:\Dev\fluxghost-win-latest-x64.zip fluxghost-win-latest-x64 > ../rar_log
cd C:\Dev\fluxghost
dist\fluxghost-win-latest-x64\ghost\ghost.exe --assets=C:\Dev\web-panel\public
