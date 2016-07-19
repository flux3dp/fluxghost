#!/usr/bin/env python3

import argparse
import sys
import os

from fluxghost.launcher import setup_env, show_version


def main():
    parser = argparse.ArgumentParser(description='FLUX Ghost')
    parser.add_argument("--assets", dest='assets', type=str,
                        default=None, help="Assets folder")
    parser.add_argument("--ip", dest='ipaddr', type=str, default='127.0.0.1',
                        help="Bind to IP Address")
    parser.add_argument("--port", dest='port', type=int, default=8000,
                        help="Port")
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
                        default='../Slic3r/slic3r.pl',
                        help="Set slic3r location")
    parser.add_argument("--cura", dest='cura', type=str,
                        default='',
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

    if options.debug:
        os.environ["flux_debug"] = "1"

    from fluxghost.http_server import HttpServer

    if options.test:
        from tests.main import main
        main()
        sys.exit(0)

    if options.simulate:
        os.environ["flux_simulate"] = "1"

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

    server.serve_forever()

if __name__ == '__main__':
    from fluxghost import __version__ as ghost_version
    from fluxclient import __version__ as client_version
    print("fluxghost: {}, fluxclient: {}".format(ghost_version, client_version), file=sys.stderr)
    main()
