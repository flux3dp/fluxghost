#!/bin/bash
#cd to script folder
cd $(dirname $0)
#run
cd ..
./dist/fluxghost-osx-latest/flux_api/flux_api --assets=../web-panel/public --slic3r=../Slic3r/slic3r
cd tools