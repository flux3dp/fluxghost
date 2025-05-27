import importlib
import re

ROUTES = [
    (re.compile('discover'), 'fluxghost.websocket.discover.WebsocketDiscover'),
    (re.compile('touch'), 'fluxghost.websocket.touch.WebsocketTouch'),
    (
        re.compile('device-manager/(?P<uuid>[0-9a-fA-F]{32})'),
        'fluxghost.websocket.device_manager.WebsocketDeviceManager',
    ),
    (
        re.compile('device-manager/usb/(?P<usb_addr>[0-9]{1,3})'),
        'fluxghost.websocket.device_manager.WebsocketDeviceManager',
    ),
    (re.compile(r'device-manager/uart/(?P<uart>[\w\W]+)'), 'fluxghost.websocket.device_manager.WebsocketDeviceManager'),
    (re.compile('control/(?P<uuid>[0-9a-fA-F]{32})'), 'fluxghost.websocket.control.WebsocketControl'),
    (re.compile('control/usb/(?P<usb_addr>[0-9]{1,3})'), 'fluxghost.websocket.control.WebsocketControl'),
    (re.compile('camera/(?P<uuid>[0-9a-fA-F]{32})'), 'fluxghost.websocket.camera.WebsocketCamera'),
    (re.compile('camera/usb/(?P<usb_addr>[0-9]{1,3})'), 'fluxghost.websocket.camera.WebsocketCamera'),
    (re.compile('usb/interfaces'), 'fluxghost.websocket.usb_interfaces.WebsocketUsbInterfaces'),
    (re.compile('usb-config'), 'fluxghost.websocket.usb_config.WebsocketUsbConfig'),
    (re.compile('ver'), 'fluxghost.websocket.ver.WebsocketVer'),
    (re.compile('svgeditor-laser-parser'), 'fluxghost.websocket.toolpath.WebsocketLaserSvgeditor'),
    (re.compile('fcode-reader'), 'fluxghost.websocket.fcode_reader.WebsocketFcodeReader'),
    (re.compile('camera-calibration'), 'fluxghost.websocket.camera_calibration.WebsocketCameraCalibration'),
    (re.compile('camera-transform'), 'fluxghost.websocket.camera_transform.WebsocketCameraTransform'),
    (re.compile('image-tracer'), 'fluxghost.websocket.image_tracer.WebsocketImageTracer'),
    (re.compile('push-studio'), 'fluxghost.websocket.push_studio.WebsocketPushStudio'),
    (re.compile('inter-process'), 'fluxghost.websocket.inter_process.WebsocketInterProcess'),
    (re.compile('opencv'), 'fluxghost.websocket.opencv.WebsocketOpenCV'),
    (re.compile('utils'), 'fluxghost.websocket.utils.WebsocketUtils'),
]


def get_match_ws_service(path):
    for exp, module_path in ROUTES:
        match = exp.match(path)
        if match:
            module_name, klass_name = module_path.rsplit('.', 1)
            module_instance = importlib.import_module(module_name)
            klass = module_instance.__getattribute__(klass_name)
            return klass, match.groupdict()
    return None, None
