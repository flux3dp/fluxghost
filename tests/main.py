

from importlib import import_module
import sys


def try_import(module_name):
    try:
        sys.stdout.write("Import %s ... " % module_name)
        sys.stdout.flush()

        m = import_module(module_name)

        sys.stdout.write("OK\n")
        sys.stdout.flush()
    except ImportError as e:
        sys.stdout.write("ERROR: %s" % e)
        sys.stdout.flush()


def main():
    try_import("scipy")
    try_import("scipy.interpolate.rbf")
    try_import("Crypto")
    try_import("serial")
    try_import("PIL")
    try_import("numpy")
    try_import("zipimport")

    try_import("fluxclient")
    try_import("fluxclient.fcode")
    try_import("fluxclient.hw_profile")
    try_import("fluxclient.laser")
    try_import("fluxclient.printer")
    try_import("fluxclient.printer._printer")
    try_import("fluxclient.robot")
    try_import("fluxclient.scanner")
    try_import("fluxclient.scanner._scanner")
    try_import("fluxclient.upnp")

