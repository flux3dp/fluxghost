
import logging
import json
import getpass
from uuid import UUID

from fluxclient.encryptor import KeyObject
from fluxclient.upnp.task import UpnpTask
from fluxclient.upnp import UpnpError

from .misc import BinaryHelperMixin, OnTextMessageMixin

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


def upnp_api_mixin(cls):
    class UpnpApi(BinaryHelperMixin, OnTextMessageMixin, cls):
        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)

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

        def on_text_message(self, message):
            try:
                if not self.has_binary_helper():
                    message = message.rstrip().split(maxsplit=1)
                    if len(message) == 1:
                        cmd = message[0]
                        params = ''
                    else:
                        cmd = message[0]
                        params = message[1]

                    if cmd in self.cmd_mapping:
                        self.cmd_mapping[cmd][0](params, *self.cmd_mapping[cmd][1:])
                    else:
                        logger.exception("receive message: %s" % (message))
                        raise ValueError('Undefine command %s' % (cmd))
                else:
                    logger.exception("receive message: %s" % (message))
                    raise RuntimeError("PROTOCOL_ERROR", "under uploading mode")

            except UpnpError as err:
                logger.exception("UpnpError message: %s" % (err.args[0]))
                self.send_fatal(*err.err_symbol, suberror=err.args[0])
                return

            except ValueError:
                logger.exception("receive message: %s" % (message))
                self.send_fatal("BAD_PARAM_TYPE")

            except RuntimeError as e:
                logger.exception("receive message: %s" % (message))
                self.send_fatal(e.args[0])

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
                self.uuid = params[0].strip()
                params = "{}"
            else:
                self.uuid, params = params
            logger.debug('connect: ' + self.uuid)

            self.uuid = UUID(hex=self.uuid)

            params = json.loads(params)
            # uuid, client_key, ipaddr=None, device_metadata=None,
            #          backend_options={}, lookup_callback=None,
            #          lookup_timeout=float("INF")
            valid_params = {'client_key': self.client_key, 'uuid': self.uuid}
            for i in ['ipaddr', 'device_metadata', 'backend_options', 'lookup_callback', 'lookup_timeout']:
                if i in params:
                    valid_params[i] = params[i]

            if self.password:
                valid_params['backend_options'] = valid_params.get('backend_options', {})
                valid_params['backend_options']['password'] = self.password

            if 'uuid' in valid_params and valid_params["client_key"]:
                self.upnp_task = UpnpTask(**valid_params)
                if self.upnp_task.authorized:
                    self.send_ok()
                    print('rsa success')
                elif self.password:  # rsa connection fail
                    try:
                        self.upnp_task.authorize_with_password(self.password)
                        if self.upnp_task.authorized:
                            self.send_ok()
                            print('pass success')
                    except:
                        self.send_error('UPNP_PASSWORD_FAIL')
                        print('pass fail')
                else:
                    self.send_error('UPNP_CONNECTION_FAIL')
                    print('rsa fail')

            else:
                self.send_fatal('API_FAIL')
                print('valid_params', valid_params)

        @check_task
        def scan_wifi(self, params):
            logger.debug('scan_wifi')
            self.send_json(status="ok", wifi=self.upnp_task.get_wifi_list())

        @check_task
        def add_key(self, params):
            """
            add current client_key into trust list
            """
            label = params.strip()
            if not label:
                label = getpass.getuser()
            logger.debug('add_key ' + label + ' ' + self.client_key.get_access_id())
            self.upnp_task.add_trust(label, self.client_key.public_key_pem.decode())
            self.send_ok()

        @check_task
        def config_network(self, params):
            logger.debug('config_network')
            options = json.loads(params)
            self.upnp_task.modify_network(**options)
            self.send_ok()

        @check_task
        def set_password(self, params):
            logger.debug('set_password')
            old, new = params.split()
            try:
                self.upnp_task.modify_password(old, new)
            except UpnpError:
                self.send_error('password changing fail')
            else:
                self.send_ok()

        @check_task
        def set_name(self, params):
            new_name = params.strip()
            logger.debug('set_name ' + new_name)
            print(new_name)
            self.upnp_task.rename(new_name)
            print('rename done')
            self.send_ok()

        def on_close(self, message):
            self.close_task()
            super().on_close(message)

        def close_task(self):
            logger.debug('close_task')
            if self.upnp_task:
                self.upnp_task.close()
                self.upnp_task = None
    return UpnpApi
