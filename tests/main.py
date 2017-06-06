

from importlib import import_module
import sys

from fluxghost.http_websocket_route import ROUTES


def try_import(module_name):
    try:
        sys.stdout.write("Import %s ... " % module_name)
        sys.stdout.flush()

        import_module(module_name)

        sys.stdout.write("OK\n")
        sys.stdout.flush()
        return True
    except ImportError as e:
        sys.stdout.write("ERROR: %s" % e)
        sys.stdout.flush()
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
    "fluxclient.printer",
    "fluxclient.printer._printer",
    "fluxclient.robot",
    "fluxclient.scanner",
    "fluxclient.scanner._scanner",
    "fluxclient.upnp",
] + [m.rsplit(".", 1)[0] for p, m in ROUTES]


def main():
    ret = True
    for m in TEST_MODULES:
        ret &= try_import(m)

    sys.stdout.write("Open resource fluxclient::assets/flux3dp-icon.png ... ")
    sys.stdout.flush()
    try:
        import pkg_resources
        pkg_resources.resource_stream("fluxclient", "assets/flux3dp-icon.png")
        sys.stdout.write("OK\n")
    except Exception as e:
        sys.stdout.write("ERROR: %s" % e)
        sys.stdout.flush()
        ret = False

    return 0 if ret else 1
