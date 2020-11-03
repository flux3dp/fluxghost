bash -c "set -e 1; export LC_ALL=\"en_US.UTF-8\"; export LC_CTYPE=\"en_US.UTF-8\"; pyinstaller --noconfirm --clean ghost.spec"
sudo cp -R /Library/Frameworks/Python.framework/Versions/3.6/lib/tcl8.6 dist/flux_api/tcl
sudo cp -R /Library/Frameworks/Python.framework/Versions/3.6/lib/tk8.6 dist/flux_api/tk