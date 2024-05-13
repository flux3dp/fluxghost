#!/bin/bash
#cd to script folder
cd $(dirname $0)
cd ..
git stash -u
python3 ./tools/type_hint_remover.py fluxghost
cd ..
tar -zcvf ./fluxghost/fluxghost.tar.gz --exclude="__pycache__" --exclude="lib/" --exclude="tools/" --exclude="dist/" --exclude="build/"  --exclude="node_modules/" --exclude="*.yml" --exclude="*.spec" --exclude=".git/" --exclude=".vscode/" --exclude="*.pyc" --exclude=".DS_Store" ./fluxghost
cd fluxghost
git reset --hard
git stash pop
