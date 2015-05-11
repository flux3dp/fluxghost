
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
(YOURENV)# pip install pysendfile
(YOURENV)# pip install pycrypto
```

5. Launch fluxghost
```
(YOURENV)# ./bin/fluxghost -d
```