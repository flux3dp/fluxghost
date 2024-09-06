#!/bin/bash
cd $(dirname $0)
# fluxghost
cd ../..
docker build -f fluxghost/docker/DockerFile -t fluxghost .

