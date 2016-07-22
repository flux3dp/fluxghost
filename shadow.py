#!/usr/bin/env python3

import argparse
import sys
import os

from fluxghost.pipe_route import get_match_pipe_service, ROUTES
from fluxghost.launcher import setup_env, show_version


def main():
    parser = argparse.ArgumentParser(description='FLUX Shadow')
    parser.add_argument("--log", dest='logfile', type=str, default=None,
                        help="Output log to specific")
    parser.add_argument('-d', '--debug', dest='debug', action='store_const',
                        const=True, default=False, help='Enable debug')
    parser.add_argument('-s', '--simulate', dest='simulate',
                        action='store_const', const=True, default=False,
                        help='Simulate data')
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
    parser.add_argument(dest='task', choices=ROUTES.keys(), help='Task')
    parser.add_argument(dest='arguments', type=str, nargs='*',
                        help='Task args')

    options = parser.parse_args()
    if options.version:
        show_version(options.debug)
        sys.exit(0)

    setup_env(options)

    if options.test:
        from tests.main import main
        main()
        sys.exit(0)

    if options.slic3r:
        os.environ["slic3r"] = options.slic3r

    if options.cura:
        os.environ["cura"] = options.cura

    klass = get_match_pipe_service(options.task)
    instance = klass(sys.stdin.buffer, sys.stdout.buffer, options,
                     *options.arguments)
    instance.serve_forever()
    return 0


if __name__ == '__main__':
    sys.exit(main())
