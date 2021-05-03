# -*- mode: python -*-

from pkg_resources import resource_listdir, resource_isdir, resource_filename, parse_version

from PyInstaller import __version__ as PyInstallerVersion
from platform import version as get_os_version

if parse_version(PyInstallerVersion) >= parse_version('3.1'):
    from PyInstaller.utils.hooks import collect_submodules
else:
    from PyInstaller.utils.hooks.hookutils import collect_submodules

import os, platform, sys, site
os_type = platform.system()
sitepackages = site.getsitepackages()

for d in sitepackages:
    if 'site-packages' in d:
        sitepackages = d
        break

def fetch_data(package, path):
    data = []
    for sys_path in os.listdir(sitepackages):
        if package == sys_path or (package == 'fluxclient' and package in sys_path):
            if package == 'fluxclient':
                sys_path = os.path.join(sitepackages, sys_path, package)
            else :
                sys_path = os.path.join(sitepackages, sys_path)
            if not os.path.isdir(sys_path):
                continue
            for fn in os.listdir(os.path.join(sys_path, path)):
                np = os.path.join(path, fn)
                fp = os.path.join(sys_path, np)
                if os.path.isdir(fp):
                    data += fetch_data(package, np)
                else:
                    data.append((os.path.join(package, np), fp, 'DATA'))
                            
    return data


def fetch_datas():
    datas = []
    packages_to_fetch = [('fluxclient', 'assets'), ('cffi', ''), ('cssselect2', ''), ('pycparser', ''), ('tinycss2', ''), ('cairocffi', '')]
    for p in packages_to_fetch:
        datas += fetch_data(p[0], p[1])
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
                  'fluxghost.websocket.image_tracer',
                  'fluxghost.websocket.inter_process',
                  'fluxghost.websocket.push_studio',
                  'fluxghost.websocket.opencv',
]

binaries = []
excludes = ["matplotlib", "pydoc", "IPython"]

if os_type.startswith('Windows'):
    print(platform.architecture()[0])
    if platform.architecture()[0] == '64bit':
        print('ghost spec x64')
        binaries.append( ('C:\\windows\\system32\\MSVCP140.dll', '.') )
        binaries.append( ('C:\\windows\\system32\\VCRUNTIME140.dll', '.') )
        binaries.append( ('C:\\windows\\system32\\VCRUNTIME140_1.dll', '.') )
        binaries.append( ('.\\lib\\x64\\libusb0.dll', '.') )
        binaries.append( ('.\\lib\\x64\\libcairo-2.dll', '.') )
        binaries.append( ('.\\lib\\x64\\libpixman-1-0.dll', '.') )
        binaries.append( ('.\\lib\\x64\\libfreetype-6.dll', '.') )
        binaries.append( ('.\\lib\\x64\\libfontconfig-1.dll', '.') )
        binaries.append( ('.\\lib\\x64\\libpng16-16.dll', '.') )
        binaries.append( ('.\\lib\\x64\\libxml2-2.dll', '.') )
        binaries.append( ('.\\lib\\x64\\zlib1.dll', '.') )
        binaries.append( ('.\\lib\\x64\\libexpat-1.dll', '.') )
        binaries.append( ('.\\lib\\x64\\libgcc_s_sjlj-1.dll', '.') )
        binaries.append( ('.\\lib\\x64\\libharfbuzz-0.dll', '.') )
        binaries.append( ('.\\lib\\x64\\libiconv-2.dll', '.') )
        binaries.append( ('.\\lib\\x64\\libwinpthread-1.dll', '.') )
        binaries.append( ('.\\lib\\x64\\liblzma-5.dll', '.') )
    else:
        print('ghost spec x86')
        binaries.append( ('C:\\windows\\system32\\MSVCP140.dll', '.') )
        binaries.append( ('C:\\windows\\system32\\VCRUNTIME140.dll', '.') )
        binaries.append( ('.\\lib\\x32\\libusb0.dll', '.') )
        binaries.append( ('.\\lib\\x32\\libcairo-2.dll', '.') )
        binaries.append( ('.\\lib\\x32\\freetype6.dll', '.') )
        binaries.append( ('.\\lib\\x32\\libfontconfig-1.dll', '.') )
        binaries.append( ('.\\lib\\x32\\libpng12-0.dll', '.') )
        binaries.append( ('.\\lib\\x32\\libpixman-1-0.dll', '.') )
        binaries.append( ('.\\lib\\x32\\zlib1.dll', '.') )
        binaries.append( ('.\\lib\\x32\\libexpat-1.dll', '.') )
    for file in os.listdir('.\\lib\\win'):
        path = os.path.join('.\\lib\\win', file)
        binaries.append( (path, '.') )
elif os_type.startswith('Darwin'):
    binaries.append( ('./lib/mac/libcairo.dylib', '.') )
    binaries.append( ('./lib/mac/libcairo.2.dylib', '.') )
    binaries.append( ('./lib/mac/libcairo-gobject.dylib', '.') )
    binaries.append( ('./lib/mac/libcairo-gobject.2.dylib', '.') )
    binaries.append( ('./lib/mac/libfreetype.6.dylib', '.') )
    binaries.append( ('./lib/mac/libpixman-1.0.dylib', '.') )
    binaries.append( ('./lib/mac/libfontconfig.1.dylib', '.') )
    binaries.append( ('./lib/mac/libpng16.16.dylib', '.') )
    binaries.append( ('/usr/lib/libz.1.dylib', '.') )
    if get_os_version().startswith("Darwin Kernel Version 17"):
        binaries.append( ('/opt/X11/lib/libXrender.1.dylib', '.') )
        binaries.append( ('/opt/X11/lib/libxcb.1.dylib', '.') )
        binaries.append( ('/opt/X11/lib/libXau.6.dylib', '.') )
        binaries.append( ('/opt/X11/lib/libXdmcp.6.dylib', '.') )
        binaries.append( ('/opt/X11/lib/libSM.6.dylib', '.') )
        binaries.append( ('/opt/X11/lib/libICE.6.dylib', '.') )
        binaries.append( ('/opt/X11/lib/libX11.6.dylib', '.') )
        binaries.append( ('/opt/X11/lib/libXext.6.dylib', '.') )
    else:
        pass
    excludes.append("win32com")
elif os_type.startswith('Linux'):
    # binaries.append( ('/usr/local/lib/libcairo.so.2', '.') )
    excludes.append("win32com")
else:
    raise ValueError('Unknown Os Type {}'.format(os_type) )

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

# print('Datas:')
# for d in a.datas:
#   print(d)
# print('=====')

# print('Hidden imports:')
# for h in a.hiddenimports:
#   print(h)
# print('=====')

# print('Binaries:')
# for b in a.binaries:
#   print(b)
# print('=====')

coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=None,
               upx=True,
               name='flux_api')
