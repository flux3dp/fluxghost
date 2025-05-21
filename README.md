# FLUXGhost

FLUXGhost provides a websocket based API for FLUX-Studio frontend, which connects to fluxclient.

Official site: <http://flux3dp.com/>  
Official forum: <http://forum.flux3dp.com/>  
Official documentation: <http://dev.flux3dp.com/>  

## Features

* Websocket based API for controlling your FLUX Delta.

## Installation and Usage

1. Install docker and docker compose.
2. Clone fluxclient(-dev), beamify, fluxsvg from github
3. Launch fluxghost

    ```sh
      docker compose build
      docker compose up -d
    ```

4. To shutdown the server, run

    ```sh
      docker compose down
    ```

## Compilation ( for FLUX Studio )

1. Install pyinstaller

    ```sh
    pip3 install pyinstaller
    ```

2. Run `pyinstaller ghost.spec` at fluxghost's root directory
3. Binary files will be in ./dist/ghost
