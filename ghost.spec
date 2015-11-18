# -*- mode: python -*-

block_cipher = None


a = Analysis(['ghost.py'],
             pathex=['/Users/Cerberus/Projects/python/py33/flux3dp/fluxghost'],
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
               "fluxghost.websocket.stl_slicing_parser",
               "fluxghost.websocket.touch",
               "fluxghost.websocket.usb_config"],
             hookspath=None,
             runtime_hooks=None,
             excludes=None,
             cipher=block_cipher)
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
