# -*- mode: python -*-

from pkg_resources import resource_listdir, resource_isdir, resource_filename, parse_version

from PyInstaller import __version__ as PyInstallerVersion
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
                 "scipy.integrate",
                 "scipy.interpolate.rbf",
                 "scipy.linalg.cython_blas",
                 "scipy.linalg.cython_lapack"]
hiddenimports += collect_submodules("fluxclient")


hiddenimports += collect_submodules("fluxghost")  # this is not working, manually hotfix below
hiddenimports += ['fluxclient.scanner.pc_process',
                  'fluxclient.commands.discover',
                  'fluxclient.upnp.task',
                  'fluxclient.fcode',
                  'fluxclient.commands.fcode',
                  'fluxclient.commands.scan',
                  'fluxclient.upnp.discover',
                  'fluxclient.usb.task',
                  'fluxclient.printer._printer',
                  'fluxclient.commands.robot',
                  'fluxclient.printer.flux_raft',
                  'fluxclient.scanner.image_to_pc',
                  'fluxclient.robot.misc',
                  'fluxclient.laser',
                  'fluxclient.upnp.base',
                  'fluxclient.utils.fcode_parser',
                  'fluxclient',
                  'fluxclient.scanner._scanner',
                  'fluxclient.laser.laser_svg',
                  'fluxclient.utils',
                  'fluxclient.hw_profile',
                  'fluxclient.usb.misc',
                  'fluxclient.utils.svg_parser',
                  'fluxclient.scanner',
                  'fluxclient.laser.pen_svg',
                  'fluxclient.encryptor',
                  'fluxclient.usb',
                  'fluxclient.scanner.freeless',
                  'fluxclient.robot.base',
                  'fluxclient.commands.config_network',
                  'fluxclient.commands.usb',
                  'fluxclient.laser.tools',
                  'fluxclient.scanner.tools',
                  'fluxclient.upnp.misc',
                  'fluxclient.robot.sock_v0002',
                  'fluxclient.printer.stl_slicer',
                  'fluxclient.laser.laser_base',
                  'fluxclient.upnp',
                  'fluxclient.commands.experiment_tool',
                  'fluxclient.commands',
                  'fluxclient.fcode.fcode_base',
                  'fluxclient.utils.mimetypes',
                  'fluxclient.robot',
                  'fluxclient.robot.v0002',
                  'fluxclient.commands.laser',
                  'fluxclient.utils.version',
                  'fluxclient.console',
                  'fluxclient.commands.passwd',
                  'fluxclient.robot.sock_base',
                  'fluxclient.robot_console',
                  'fluxclient.fcode.g_to_f',
                  'fluxclient.commands.auth',
                  'fluxclient.laser.laser_bitmap',
                  'fluxclient.scanner.scan_settings',
                  'fluxclient.printer']

a = Analysis(['ghost.py'],
             hiddenimports=hiddenimports,
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
