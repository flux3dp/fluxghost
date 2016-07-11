## FLUXGhost

FLUXGhost provides a websocket based API for FLUX-Studio frontend, which connects to fluxclient.

Official site: http://flux3dp.com/  
Official forum: http://forum.flux3dp.com/  
Official documentation: http://dev.flux3dp.com/  

## Features

* Websocket based API for controlling your FLUX Delta.

## Installation

1. Install Python 3.4 (or newer).
2. Install required packages

```
$ pip3 install pycrypto
$ pip3 install cython
```

3. Install fluxclient
```
cd [where fluxclient repository is]
if you didn't install pcl:
  $ python3 ./setup.py develop --without-pcl
else:
  $ python3 ./setup.py develop
```

6. Launch fluxghost
```
$ python3 ./ghost.py --ip 0.0.0.0 --port 10000
```

Use `./ghost.py --help` to check what kind of options you can use.


## Compilining to binary ( for FLUX Studio )

1. Install pyinstaller

```
$ pip3 install pyinstaller
```
2. Run `pyinstaller ghost.spec` at fluxghost top work directory

3. The binary files will be in ./dist/ghost
