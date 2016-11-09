from fluxclient.upnp import UpnpDiscover
from fluxclient.encryptor import KeyObject
from fluxclient.upnp import discover_device, UpnpError
from fluxclient.commands.misc import get_or_create_default_key
from sys import argv
import os

my_rsakey = get_or_create_default_key("./sdk_connection.pem")

discovered_device = []

def my_func_device_discover(upnp_discover, device, **kw):
    ip = str(device.ipaddr)

    if device.status['st_id'] is None:
        return

    # Test if the machine authorized
    if (not ip in discovered_device):
        print("Device '%s' found at %s with st_id %s" % (device.name, ip, device.status['st_id']))
        discovered_device.append(ip)
        status = int(device.status['st_id'])
        if (status == 16 or status == 48):
            print("Skip running device")
            return
        if (device.version == argv[2]):
            print("Skip latest version")
            return
        print("Auth %s" % device.name)
        my_func_auth_device(device)

def my_func_auth_device(my_device):
    upnp_task = my_device.manage_device(my_rsakey)

    if upnp_task.authorized:
        my_func_connect_robot(my_device)
    else:
        try:
            upnp_task.authorize_with_password("flux") #It's the same password you entered in FLUX Studio's configuration page.
            upnp_task.add_trust("my_public_key", my_rsakey.public_key_pem.decode())
            print("Authorized %s" % my_device.name)
            my_func_connect_robot(my_device)
        except UpnpError as e:
            print("Authorization failed: %s" % e)
            raise

def cb_upload_callback(robot, sent, size):
    print("Uploading %d / %d" % (sent, size))

def my_func_connect_robot(my_device):
    the_firmware = open(argv[1], 'rb')
    size = os.stat(argv[1]).st_size
    robot = my_device.connect_robot(my_rsakey)
    try:
        robot.update_firmware(the_firmware, int(size), cb_upload_callback)
        print("Update success")
    except:
        print("Update failed")
        pass

upnp_discover = UpnpDiscover()
upnp_discover.discover(my_func_device_discover)