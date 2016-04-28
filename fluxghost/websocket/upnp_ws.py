
from glob import glob
import logging
import json
import sys
from uuid import UUID

from serial.tools import list_ports as _list_ports
from fluxclient.encryptor import KeyObject
# from fluxclient.upnp import UpnpDiscover
from fluxclient.upnp.task import UpnpTask
from fluxclient.upnp import UpnpError
from .base import WebSocketBase, WebsocketBinaryHelperMixin, BinaryUploadHelper, SIMULATE, OnTextMessageMixin

logger = logging.getLogger(__name__)


def check_task(func):
    '''
    check whether it's connected to a delta
    or send_error
    '''
    def f(self, *args, **kwargs):
        if self.upnp_task:
            return func(self, *args, **kwargs)
        else:
            self.send_error('Not connected')
            return
    return f


class WebsocketUpnp(OnTextMessageMixin, WebsocketBinaryHelperMixin, WebSocketBase):

    def __init__(self, *args, **kw):
        super(WebsocketUpnp, self).__init__(*args, **kw)

        self.client_key = None
        self.password = None
        self.upnp_task = None
        self.cmd_mapping = {
            'connect': [self.connect],
            'scan_wifi': [self.scan_wifi],
            'upload_key': [self.upload_key],
            'upload_password': [self.upload_password],
            'add_key': [self.add_key],
            'config_network': [self.config_network],
            'set_name': [self.set_name],
            'set_password': [self.set_password],
        }

    def upload_key(self, params):
        logger.debug('upload_key:' + params)
        pem = params
        self.client_key = KeyObject.load_keyobj(pem)
        self.send_json(status="ok")

    def upload_password(self, params):
        logger.debug('upload_password: ' + params)
        self.password = params.strip()
        self.send_json(status="ok")

    def connect(self, params):

        self.close_task()
        params = params.split(None, 1)
        if len(params) == 1:
            uuid = params[0].strip()
            params = "{}"
        else:
            uuid, params = params
        logger.debug('connect: ' + uuid)

        uuid = UUID(hex=uuid)

        params = json.loads(params)
        # uuid, client_key, ipaddr=None, device_metadata=None,
        #          remote_profile=None, backend_options={}, lookup_callback=None,
        #          lookup_timeout=float("INF")
        valid_patams = {'client_key': self.client_key, 'uuid': uuid}
        for i in ['ipaddr', 'device_metadata', 'remote_profile', 'backend_options', 'lookup_callback', 'lookup_timeout']:
            if i in params:
                valid_patams[i] = params[i]

        if self.password:
            valid_patams['backend_options'] = valid_patams.get('backend_options', {})
            valid_patams['backend_options']['password'] = self.password

        if 'uuid' in valid_patams and valid_patams["client_key"]:
            self.upnp_task = UpnpTask(**valid_patams)
            self.send_ok()
        else:
            self.send_fatal('api fail')
            print('valid_patams', valid_patams)

    @check_task
    def scan_wifi(self, params):
        logger.debug('scan_wifi')
        self.send_json(status="ok", wifi=self.upnp_task.get_wifi_list())

    @check_task
    def add_key(self, params):
        logger.debug('add_key')
        self.upnp_task.add_trust()

    @check_task
    def config_network(self, params):
        logger.debug('config_network')
        options = json.loads(params)
        self.task.config_network(options)
        self.send_text('{"status": "ok"}')

    @check_task
    def set_password(self, params):
        logger.debug('set_password')
        old, new = params.split()
        try:
            self.task.modify_password(old, new)
        except UpnpError:
            self.send_error('password changing fail')
        else:
            self.send_ok()

    @check_task
    def set_name(self, params):
        logger.debug('set_name')
        new_name = params.strip()
        self.task.rename(new_name)
        self.send_ok()

    def on_close(self, message):
        logger.debug('on_close')
        self.close_task()

    def close_task(self):
        logger.debug('close_task')
        if self.upnp_task:
            self.upnp_task.close()
            self.upnp_task = None
