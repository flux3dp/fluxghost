

from importlib import import_module
import sys

from fluxghost.http_websocket_route import ROUTES


def try_import(module_name, without_pcl):
    try:
        sys.stdout.write("Import %s ... " % module_name)
        sys.stdout.flush()

        import_module(module_name)

        sys.stdout.write("OK\n")
        sys.stdout.flush()
        return True
    except ImportError as e:
        sys.stdout.write("ERROR: %s\n" % e)
        sys.stdout.flush()
        if without_pcl and module_name in ['fluxclient.scanner._scanner', 'fluxghost.websocket.scan_modeling']:
            sys.stdout.write("Test without pcl, so it's OK\n")
            return True
        return False


TEST_MODULES = [
    "scipy",
    "scipy.interpolate.rbf",
    "Crypto",
    "serial",
    "PIL",
    "numpy",
    "zipimport",

    "fluxclient",
    "fluxclient.fcode",
    "fluxclient.hw_profile",
    "fluxclient.laser",
    "fluxclient.robot",
    "fluxclient.scanner",
    "fluxclient.scanner._scanner",
] + [m.rsplit(".", 1)[0] for p, m in ROUTES]


def main(without_pcl):
    ret = True
    for m in TEST_MODULES:
        ret &= try_import(m, without_pcl)

    sys.stdout.write("Open resource fluxclient::assets/flux3dp-icon.png ... ")
    sys.stdout.flush()
    try:
        import pkg_resources
        pkg_resources.resource_stream("fluxclient", "assets/flux3dp-icon.png")
        sys.stdout.write("OK\n")
    except Exception as e:
        sys.stdout.write("ERROR: %s\n" % e)
        sys.stdout.flush()
        ret = False

    return 0 if ret else 1
