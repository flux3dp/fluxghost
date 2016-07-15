
import importlib

ROUTES = {
    "discover": "fluxghost.pipe.discover.PipeDiscover"
}


def get_match_pipe_service(task):
    if task in ROUTES:
        module_name, klass_name = ROUTES[task].rsplit(".", 1)
        module_instance = importlib.import_module(module_name)
        klass = module_instance.__getattribute__(klass_name)
        return klass
