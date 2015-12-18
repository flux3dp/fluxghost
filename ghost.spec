# -*- mode: python -*-

from pkg_resources import resource_listdir, resource_isdir, resource_filename
import os


def fetch_data(package, path):
    data = []
    for fn in resource_listdir(package, path):
        np = os.path.join(path, fn)
        if resource_isdir(package, np):
            data += fetch_data(package, np)
        else:
            data.append((os.path.join(package, np),
                         resource_filename(package, np),
                         'DATA'))
    return data


def fetch_datas():
    datas = []
    datas += fetch_data("fluxclient", "assets")
    return datas


block_cipher = None


a = Analysis(['ghost.py'],
             hiddenimports=[
               "serial",
               "fluxclient.printer._printer",
               "fluxclient.scanner._scanner",
               "fluxghost.websocket",
               "fluxghost.websocket.config",
               "fluxghost.websocket.control",
               "fluxghost.websocket.discover",
               "fluxghost.websocket.echo",
               "fluxghost.websocket.file",
               "fluxghost.websocket.laser_bitmap_parser",
               "fluxghost.websocket.laser_svg_parser",
               "fluxghost.websocket.scan_control",
               "fluxghost.websocket.scan_modeling",
               "fluxghost.websocket.fcode_reader",
               "fluxghost.websocket.stl_slicing_parser",
               "fluxghost.websocket.touch",
               "fluxghost.websocket.usb_config"],
             hookspath=None,
             runtime_hooks=None,
             excludes=None,
             cipher=block_cipher)
a.datas += fetch_datas()
pyz = PYZ(a.pure,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          exclude_binaries=True,
          name='ghost',
          debug=False,
          strip=None,
          upx=True,
          console=True )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=None,
               upx=True,
               name='ghost')
