cd ..
pyinstaller ghost.spec
mkdir dist/fluxghost-osx-latest
mv dist/ghost dist/fluxghost-osx-latest/ghost
cd dist
zip -r fluxghost-osx-latest.zip fluxghost-osx-latest
mv fluxghost-osx-latest.zip ../fluxghost-osx-latest.zip
cd ../tools
