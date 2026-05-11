#!/usr/bin/env python3
"""Fetch SSL certificates from the provisioner and save them locally."""

import hashlib
import hmac
import json
import logging
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import CERT_DIR

logger = logging.getLogger(__name__)

SERVER_URL = os.getenv('FLUX_GHOST_CERT_SERVER_URL', '')
SHARED_SECRET = os.getenv('FLUX_GHOST_CERT_SECRET', '')


def make_auth_headers(secret: str) -> dict:
    timestamp = str(int(time.time()))
    signature = hmac.new(secret.encode(), timestamp.encode(), hashlib.sha256).hexdigest()
    return {'x-timestamp': timestamp, 'x-signature': signature}


def _hash_local_certs() -> str:
    """Return SHA-256 hash of local cert files, or empty string if missing."""
    h = hashlib.sha256()
    for name in ('fullchain.pem', 'privkey.pem'):
        path = os.path.join(CERT_DIR, name)
        try:
            with open(path, 'rb') as f:
                h.update(f.read())
        except FileNotFoundError:
            return ''
    return h.hexdigest()


def _check_needs_update() -> bool:
    """Ask the server if local certs are up to date."""
    local_hash = _hash_local_certs()
    if not local_hash:
        return True

    url = '{}/v1/check-certs'.format(SERVER_URL)
    headers = make_auth_headers(SHARED_SECRET)
    headers['x-cert-hash'] = local_hash
    req = Request(url, headers=headers)

    try:
        with urlopen(req) as resp:
            data = json.loads(resp.read())
        return not data['up_to_date']
    except (HTTPError, URLError):
        return True  # fetch anyway if check fails


def fetch_certs():
    try:
        if not SERVER_URL or not SHARED_SECRET:
            logger.warning('Certificate server URL or secret not set, skipping certificate fetch.')
            return True

        if not _check_needs_update():
            logger.info('Certificates are up to date, skipping download.')
            return True

        url = '{}/v1/download-certs'.format(SERVER_URL)
        headers = make_auth_headers(SHARED_SECRET)
        req = Request(url, headers=headers)

        try:
            with urlopen(req) as resp:
                data = json.loads(resp.read())
        except HTTPError as e:
            logger.error('Error: server returned %s, detail: %s', e.code, e.read().decode())
            return False
        except URLError as e:
            logger.error('Error: could not connect to server: %s', e.reason)
            return False

        os.makedirs(CERT_DIR, exist_ok=True)

        fullchain_path = os.path.join(CERT_DIR, 'fullchain.pem')
        privkey_path = os.path.join(CERT_DIR, 'privkey.pem')

        with open(fullchain_path, 'w') as f:
            f.write(data['fullchain'])

        with open(privkey_path, 'w') as f:
            f.write(data['privkey'])

        logger.info('Certificates saved to %s', CERT_DIR)
        logger.info('Domain: %s', data['domain'])

        return True
    except Exception as e:
        logger.error('Error while fetching certificates: %s', e)
        return False


if __name__ == '__main__':
    res = fetch_certs()
    if not res:
        sys.exit(1)
