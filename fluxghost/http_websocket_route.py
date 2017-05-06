
import importlib
import re


ROUTES = [
    (re.compile("discover"),
     "fluxghost.websocket.discover.WebsocketDiscover"),

    (re.compile("upnp-config"),
     "fluxghost.websocket.upnp_ws.WebsocketUpnp"),
    (re.compile("touch"),
     "fluxghost.websocket.touch.WebsocketTouch"),

    (re.compile("device-manager/(?P<uuid>[0-9a-fA-F]{32})"),
     "fluxghost.websocket.device_manager.WebsocketDeviceManager"),
    (re.compile("device-manager/usb/(?P<usb_addr>[0-9]{1,3})"),
     "fluxghost.websocket.device_manager.WebsocketDeviceManager"),
    (re.compile("device-manager/uart/(?P<uart>[\w\W]+)"),
     "fluxghost.websocket.device_manager.WebsocketDeviceManager"),

    (re.compile("control/(?P<uuid>[0-9a-fA-F]{32})"),
     "fluxghost.websocket.control.WebsocketControl"),
    (re.compile("control/usb/(?P<usb_addr>[0-9]{1,3})"),
     "fluxghost.websocket.control.WebsocketControl"),

    (re.compile("camera/(?P<uuid>[0-9a-fA-F]{32})"),
     "fluxghost.websocket.camera.WebsocketCamera"),
    (re.compile("camera/usb/(?P<usb_addr>[0-9]{1,3})"),
     "fluxghost.websocket.camera.WebsocketCamera"),

    (re.compile("3d-scan-control/" + '0' * 32),
     "fluxghost.websocket.scan_control.Websocket3DScanControlSimulation"),
    (re.compile("3d-scan-control/(?P<uuid>[0-9a-fA-F]{32})"),
     "fluxghost.websocket.scan_control.Websocket3DScanControl"),
    (re.compile("3d-scan-control/usb/(?P<usb_addr>[0-9]{1,3})"),
     "fluxghost.websocket.scan_control.Websocket3DScanControl"),

    (re.compile("usb/interfaces"),
     "fluxghost.websocket.usb_interfaces.WebsocketUsbInterfaces"),
    (re.compile("usb-config"),
     "fluxghost.websocket.usb_config.WebsocketUsbConfig"),

    (re.compile("ver"),
     "fluxghost.websocket.ver.WebsocketVer"),
    (re.compile("3d-scan-modeling"),
     "fluxghost.websocket.scan_modeling.Websocket3DScannModeling"),
    (re.compile("bitmap-laser-parser"),
     "fluxghost.websocket.toolpath.WebsocketLaserBitmap"),
    (re.compile("svg-laser-parser"),
     "fluxghost.websocket.toolpath.WebsocketLaserSvg"),
    (re.compile("pen-svg-parser"),
     "fluxghost.websocket.toolpath.WebsocketDrawingSvg"),
    (re.compile("svg-vinyl-parser"),
     "fluxghost.websocket.toolpath.WebsocketVinylSvg"),
    (re.compile("fcode-reader"),
     "fluxghost.websocket.fcode_reader.WebsocketFcodeReader"),
    (re.compile("3dprint-slicing"),
     "fluxghost.websocket.stl_slicing_parser.Websocket3DSlicing")]


def get_match_ws_service(path):
    for exp, module_path in ROUTES:
        match = exp.match(path)
        if match:
            module_name, klass_name = module_path.rsplit(".", 1)
            module_instance = importlib.import_module(module_name)
            klass = module_instance.__getattribute__(klass_name)
            return klass, match.groupdict()
    return None, None
