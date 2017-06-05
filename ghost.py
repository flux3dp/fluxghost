#!/usr/bin/env python3

from signal import SIGTERM
from time import sleep
import argparse
import sys
import os

from fluxghost.launcher import setup_env, show_version


def trace_pid(pid):
    def _nt():
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            DWORD = ctypes.c_ulong  # noqa
            DWORD_PTR = ctypes.POINTER(DWORD)  # noqa
            STILL_ALIVE = 259  # noqa

            h_process = kernel32.OpenProcess(1040, 0, pid)
            if not h_process:
                raise RuntimeError("Trace pid error, pid not exist or access deny.")

            exitcode = DWORD()

            while True:
                ret = kernel32.GetExitCodeProcess(h_process, ctypes.byref(exitcode))
                if not ret:
                    raise RuntimeError("Trace pid error, errno=%s" % kernel32.GetLastError())
                elif exitcode.value == 259:
                    sleep(0.8)
                else:
                    break
        except Exception as e:
            sys.stderr.write("%s\n" % e)
        finally:
            os.kill(os.getpid(), SIGTERM)

    def _posix():
        try:
            while True:
                os.kill(pid, 0)
                sleep(0.8)
        except:
            pass
        finally:
            os.kill(os.getpid(), SIGTERM)

    from threading import Thread
    if os.name == "posix":
        fn = _posix
    elif os.name == "nt":
        fn = _nt
    else:
        raise RuntimeError("Unknown os.name %r" % os.name)

    t = Thread(target=fn)
    t.daemon = True
    t.start()


def main():
    parser = argparse.ArgumentParser(description='FLUX Ghost')
    parser.add_argument("--assets", dest='assets', type=str,
                        default=None, help="Assets folder")
    parser.add_argument("--ip", dest='ipaddr', type=str, default='127.0.0.1',
                        help="Bind to IP Address")
    parser.add_argument("--port", dest='port', type=int, default=8000,
                        help="Port")
    parser.add_argument("--trace-pid", dest="trace_pid", type=int,
                        default=None)
    parser.add_argument("--log", dest='logfile', type=str, default=None,
                        help="Output log to specific")
    parser.add_argument('-d', '--debug', dest='debug', action='store_const',
                        const=True, default=False, help='Enable debug')
    parser.add_argument('-s', '--simulate', dest='simulate',
                        action='store_const', const=True, default=False,
                        help='Simulate data')
    parser.add_argument('--allow-foreign', dest='allow_foreign',
                        action='store_const', const=True, default=False,
                        help='Allow websocket connection from foreign')

    parser.add_argument("--slic3r", dest='slic3r', type=str,
                        default=os.environ.get("GHOST_SLIC3R"),
                        help="Set slic3r location")
    parser.add_argument("--cura", dest='cura', type=str,
                        default=os.environ.get("GHOST_CURA"),
                        help="Set cura location")

    parser.add_argument("--sentry", dest='sentry', type=str, default=None,
                        help="Use sentry logger")
    parser.add_argument('--test', dest='test', action='store_const',
                        const=True, default=False, help='Run test')
    parser.add_argument('--version', dest='version', action='store_const',
                        const=True, default=False, help='Show version')

    options = parser.parse_args()
    if options.version:
        show_version(options.debug)
        sys.exit(0)

    setup_env(options)

    from fluxghost.http_server import HttpServer

    if options.test:
        from tests.main import main
        main()
        sys.exit(0)

    if options.slic3r:
        os.environ["slic3r"] = options.slic3r

    if options.cura:
        os.environ["cura"] = options.cura

    if not options.assets:
        options.assets = os.path.join(
            os.path.dirname(
                os.path.abspath(__file__)),
            "fluxghost", "assets")

    server = HttpServer(assets_path=options.assets,
                        enable_discover=True,
                        address=(options.ipaddr, options.port,),
                        allow_foreign=options.allow_foreign,
                        debug=options.debug)

    if options.trace_pid:
        trace_pid(options.trace_pid)

    server.serve_forever()


if __name__ == '__main__':
    main()
