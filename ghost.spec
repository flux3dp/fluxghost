# -*- mode: python -*-

from pkg_resources import resource_listdir, resource_isdir, resource_filename, parse_version

from PyInstaller import __version__ as PyInstallerVersion
from PyInstaller import is_win

if parse_version(PyInstallerVersion) >= parse_version('3.1'):
    from PyInstaller.utils.hooks import collect_submodules
else:
    from PyInstaller.utils.hooks.hookutils import collect_submodules

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
hiddenimports = ["serial",
                 "PIL",
                 "cv2",
                 "scipy.integrate",
                 "scipy.interpolate.rbf",
                 "scipy.linalg.cython_blas",
                 "scipy.linalg.cython_lapack"]
hiddenimports += collect_submodules("fluxclient")
hiddenimports += collect_submodules("beamify")
hiddenimports += collect_submodules("fluxsvg")
hiddenimports += collect_submodules("pkg_resources")
hiddenimports += ['fluxghost',
                  'fluxghost.http_server',
                  'fluxghost.http_handler',
                  'fluxghost.http_handlers.websocket_handler',
                  'fluxghost.http_handlers.file_handler',
                  'fluxghost.http_handlers',
                  'fluxghost.http_server_base',
                  'fluxghost.http_websocket_route',
                  'fluxghost.http_server_debug',
                  'fluxghost.utils',
                  'fluxghost.utils.websocket',
                  'fluxghost.websocket',
                  'fluxghost.websocket.touch',
                  'fluxghost.websocket.base',
                  'fluxghost.websocket.ver',
                  'fluxghost.websocket.toolpath',
                  'fluxghost.websocket.control',
                  'fluxghost.websocket.discover',
                  'fluxghost.websocket.config',
                  'fluxghost.websocket.camera',
                  'fluxghost.websocket.scan_modeling',
                  'fluxghost.websocket.stl_slicing_parser',
                  'fluxghost.websocket.scan_control',
                  'fluxghost.websocket.fcode_reader',
                  'fluxghost.websocket.echo',
                  'fluxghost.websocket.usb_config',
                  'fluxghost.websocket.upnp_ws',
                  'fluxghost.websocket.device_manager',
                  'fluxghost.websocket.usb_interfaces',
                  'fluxghost.websocket.camera_calibration',
]

binaries = []
excludes = ["matplotlib", "pydoc", "IPython"]

if is_win:
  binaries.append( ('C:\\Windows\\System32\\libusb0.dll', '.') )
else:
  excludes.append("win32com")


a = Analysis(['ghost.py'],
             hiddenimports=hiddenimports,
             excludes=excludes,
             hookspath=None,
             runtime_hooks=None,
             cipher=block_cipher,
             binaries=binaries)
a.datas += fetch_datas()
pyz = PYZ(a.pure,
          cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          exclude_binaries=True,
          name='flux_api',
          debug=False,
          strip=None,
          upx=True,
          console=True)
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=None,
               upx=True,
               name='flux_api')
