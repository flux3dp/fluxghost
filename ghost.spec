# -*- mode: python -*-

from pkg_resources import resource_listdir, resource_isdir, resource_filename, parse_version

from PyInstaller import __version__ as PyInstallerVersion
from PyInstaller import is_win, is_darwin, is_linux

if parse_version(PyInstallerVersion) >= parse_version('3.1'):
    from PyInstaller.utils.hooks import collect_submodules
else:
    from PyInstaller.utils.hooks.hookutils import collect_submodules

import os, platform


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
hiddenimports = ["cairocffi",
                 "serial",
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
hiddenimports += ['beamify',
                  'fluxsvg',
                  'fluxghost',
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
  if platform.architecture()[0] == '64bit':
    binaries.append( ('C:\\jenkins\\cairo-dll\\libcairo-2.dll', '.') )
    binaries.append( ('C:\\jenkins\\cairo-dll\\libpixman-1-0.dll', '.') )
    binaries.append( ('C:\\jenkins\\cairo-dll\\libfreetype-6.dll', '.') )
    binaries.append( ('C:\\jenkins\\cairo-dll\\libfontconfig-1.dll', '.') )
    binaries.append( ('C:\\jenkins\\cairo-dll\\libpng16-16.dll', '.') )
    binaries.append( ('C:\\jenkins\\cairo-dll\\libxml2-2.dll', '.') )
    binaries.append( ('C:\\jenkins\\cairo-dll\\zlib1.dll', '.') )
  else:
    binaries.append( ('C:\\jenkins\\cairo-dll\\libcairo-2.dll', '.') )
    binaries.append( ('C:\\jenkins\\cairo-dll\\libfreetype-6.dll', '.') )
    binaries.append( ('C:\\jenkins\\cairo-dll\\libfontconfig-1.dll', '.') )
    binaries.append( ('C:\\jenkins\\cairo-dll\\libpng12.dll', '.') )
    binaries.append( ('C:\\jenkins\\cairo-dll\\libxml2.dll', '.') )
    binaries.append( ('C:\\jenkins\\cairo-dll\\zlib1.dll', '.') )
elif is_darwin:
  binaries.append( ('/usr/local/lib/libcairo.dylib', '.') )
  binaries.append( ('/usr/local/lib/libpixman-1.0.dylib', '.') )
  binaries.append( ('/usr/local/lib/libfontconfig.1.dylib', '.') )
  binaries.append( ('/usr/local/lib/libfreetype.6.dylib', '.') )
  binaries.append( ('/usr/local/lib/libpng16.16.dylib', '.') )
  binaries.append( ('/usr/lib/libz.1.dylib', '.') )
  binaries.append( ('/opt/X11/lib/libXrender.1.dylib', '.') )
  binaries.append( ('/opt/X11/lib/libxcb.1.dylib', '.') )
  binaries.append( ('/opt/X11/lib/libXau.6.dylib', '.') )
  binaries.append( ('/opt/X11/lib/libXdmcp.6.dylib', '.') )
  binaries.append( ('/opt/X11/lib/libSM.6.dylib', '.') )
  binaries.append( ('/opt/X11/lib/libICE.6.dylib', '.') )
  binaries.append( ('/opt/X11/lib/libX11.6.dylib', '.') )
  binaries.append( ('/opt/X11/lib/libXext.6.dylib', '.') )
  excludes.append("win32com")
elif is_linux:
  binaries.append( ('/usr/local/lib/libcairo.so.2', '.') )
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
