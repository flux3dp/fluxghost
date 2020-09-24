#!/bin/bash
#cd to script folder
cd $(dirname $0)
cd ..
tar -zcvf fluxghost.tar.gz --exclude="__pycache__" --exclude="lib/" --exclude="tools/" --exclude="node_modules/" --exclude="*.yml" --exclude="*.spec" --exclude=".git/" .