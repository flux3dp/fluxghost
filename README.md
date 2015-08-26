
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
(YOURENV)# pip3 install pycrypto
```

5. Install fluxclient
```
cd [where fluxclient repository is]
if you didn't install pcl:
  (YOURENV)# python3 ./setup.py develop --without-pcl
else:
  (YOURENV)# python3 ./setup.py develop --without-pcl
```

6. Launch fluxghost
```
(YOURENV)# ./ghost.py
```

Use `./ghost.py --help` to check what kind of options you can use.
