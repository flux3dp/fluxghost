cd ..
pyinstaller ghost.spec
zip -r latest-ghost-osx.zip dist/ghost
cp latest-ghost-osx.zip /Volumes/software/fluxghost/fluxghost-$(date +%Y%m%d)-osx.zip
cd tools
