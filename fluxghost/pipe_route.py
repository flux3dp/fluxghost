
import importlib

ROUTES = {
    "discover": "fluxghost.pipe.discover.PipeDiscover",
    "3d-scan-modeling": "fluxghost.pipe.scan_modeling.Pipe3DScannModeling",
    "3dprint-slicing": "fluxghost.pipe.stl_slicing_parser.Pipe3DSlicing"
}


def get_match_pipe_service(task):
    if task in ROUTES:
        module_name, klass_name = ROUTES[task].rsplit(".", 1)
        module_instance = importlib.import_module(module_name)
        klass = module_instance.__getattribute__(klass_name)
        return klass
