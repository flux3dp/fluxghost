#!/usr/bin/env python3

from __future__ import absolute_import

import argparse
import logging
import sys

def setup_logger(debug):
    LOG_TIMEFMT = "%Y-%m-%d %H:%M:%S"
    LOG_FORMAT = "[%(asctime)s,%(levelname)s,%(name)s] %(message)s"

    logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_TIMEFMT)

    logger = logging.getLogger('')
    if debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)


parser = argparse.ArgumentParser(description='FLUX Ghost')
parser.add_argument("--assets", dest='assets', type=str,
                    default='fluxghost/assets', help="Assets folder")
parser.add_argument("--ip", dest='ipaddr', type=str, default='127.0.0.1',
                    help="Bind to IP Address")
parser.add_argument("--port", dest='port', type=int, default=8000,
                    help="Port")
parser.add_argument('-d', '--debug', dest='debug', action='store_const',
                    const=True, default=False, help='Enable debug')

options = parser.parse_args()
setup_logger(debug=options.debug)

from fluxghost.http_server import HttpServer

server = HttpServer(assets_path=options.assets,
                    address=(options.ipaddr, options.port,),)

server.serve_forever()
