
### Simple Guide ###

1. Install Python 3.3 (or newer).

2. Install virtualenv
```
# sudo pip3 install virtualenv
# virtualenv YOURENV
```

Attention: Ensure your are using correct python version

3. Enter virtualenv
```
# source YOURENV/bin/activate
(YOURENV)#
```

Note: You will see `(YOURENV)# ` in your console prompt to let you know you are in it.

4. Install depent packages

```
(YOURENV)# pip3 install pysendfile
(YOURENV)# pip3 install pycrypto
(YOURENV)# pip3 install cython
```

5. Install fluxclient
```
cd [where fluxclient repository is]
if you didn't install pcl:
  (YOURENV)# python3 ./setup.py develop --without-pcl
else:
  (YOURENV)# python3 ./setup.py develop
```

6. Launch fluxghost
```
(YOURENV)# ./ghost.py
```

Use `./ghost.py --help` to check what kind of options you can use.


### Pack ###

1. Ensure fluxclient is installed

2. Ensure pyinstaller for python 3 is installed (Note 1)

3. Just run `pyinstaller ghost.spec` at fluxghost top work directory

4. Output at ./dist/ghost is what you want

* Note 1: Install pyinstaller for python3

> 1. Download pyinstall at `https://github.com/pyinstaller/pyinstaller/tree/python3`

> 2. Remember you download pyinstall from github is branch: `python3`

> 3. Check you download pyinstall from github is branch: `python3`

> 4. Ensure you download pyinstall from github is branch: `python3`

> 5. Run `./setup.py install` at pyinstall folder work directory and done
