
import importlib

ROUTES = {
    # Device related
    "discover":
        "fluxghost.pipe.discover.PipeDiscover",
    # "upnp-config":
    #     "fluxghost.websocket.upnp_ws.WebsocketUpnp",
    # "touch":
    #     "fluxghost.websocket.touch.WebsocketTouch",
    # "control":
    #     "fluxghost.websocket.control.WebsocketControl",
    # "camera":
    #     "fluxghost.websocket.camera.WebsocketCamera",
    # "3d-scan-control":
    #     "fluxghost.websocket.scan_control.Websocket3DScanControl",
    "usb-config":
        "fluxghost.pipe.usb_config.PipeUsbConfig",

    # Data related
    "3d-scan-modeling":
        "fluxghost.pipe.scan_modeling.Pipe3DScannModeling",
    "3dprint-slicing":
        "fluxghost.pipe.stl_slicing_parser.Pipe3DSlicing",
    "bitmap-laser-parser":
        "fluxghost.pipe.laser_bitmap_parser.PipeLaserBitmapParser",
    "svg-laser-parser":
        "fluxghost.pipe.laser_svg_parser.PipeLaserSvgParser",
    "pen-svg-parser":
        "fluxghost.pipe.pen_svg_parser.PipePenSvgParser",
    "fcode-reader":
        "fluxghost.pipe.fcode_reader.PipeFcodeReader",
}


def get_match_pipe_service(task):
    if task in ROUTES:
        module_name, klass_name = ROUTES[task].rsplit(".", 1)
        module_instance = importlib.import_module(module_name)
        klass = module_instance.__getattribute__(klass_name)
        return klass
