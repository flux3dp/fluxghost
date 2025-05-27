from datetime import datetime
from random import choice, randint
from time import time

from fluxclient.robot.errors import RobotError

filesystem = {
    'USB': {
        'folders': {
            '20160301': {'folders': {}, 'files': {'tower_of_pi.fc': {}}},
            '20160304': {
                'folders': {
                    'Curiosity': {
                        'folders': {},
                        'files': {'body.fc': {}, 'components.fc': {}, 'pins-and-hubs.fc': {}, 'wheels.fc': {}},
                    }
                },
                'files': {},
            },
        },
        'files': {},
    },
    'SD': {
        'folders': {'geometry': {'folders': {}, 'files': {'spiral_orb_02.fc': {}, 'penrose4.fc': {}}}},
        'files': {'cube.fc': {}, 'king.fc': {}, 'queen.fc': {}},
    },
}


def get_simulate_path(path):
    if path.startswith('/') is False:
        path = '/' + path

    req_nodes = path.split('/')[1:]

    if not req_nodes:
        raise RobotError(error_symbol=['NOT_EXIST', 'BAD_ENTRY'])
    elif req_nodes[0] == 'SD' or req_nodes[0] == 'USB':
        node = filesystem['SD'] if req_nodes[0] == 'SD' else filesystem['USB']
        req_nodes.pop(0)

        while req_nodes:
            req_node = req_nodes.pop(0)
            new_node = node['folders'].get(req_node)
            if new_node is not None:
                node = new_node
            elif len(req_nodes) == 0:
                new_node = node['files'].get(req_node)
                if new_node is not None:
                    return False, new_node
                else:
                    raise RobotError('%s not found' % req_node, error_symbol=['NOT_EXIST', 'BAD_NODE'])
            else:
                raise RobotError('%s not found.' % req_node, error_symbol=['NOT_EXIST', 'BAD_NODE'])

        return True, node

    else:
        raise RobotError(error_symbol=['NOT_EXIST', 'BAD_ENTRY'])


def get_simulate_file_info(path):
    is_dir, node = get_simulate_path(path)
    if is_dir:
        raise RobotError('%s not file' % path, error_symbol=['NOT_EXIST', 'BAD_NODE'])

    if 'size' not in node:
        node['size'] = randint(1024, 1024 << 16)

    if path.endswith('.fc'):
        if 'AUTHOR' not in node:
            node['AUTHOR'] = 'Cute boy'
        if 'CREATED_AT' not in node:
            d = datetime.fromtimestamp(time() - randint(2 < 16, 2 << 32))
            node['CREATED_AT'] = d.strftime('%Y-%m-%dT%H:%M:%SZ')

        if 'TRAVEL_DIST' not in node:
            node['TRAVEL_DIST'] = randint(2 < 16, 2 << 40) / 1000.0
        if 'TIME_COST' not in node:
            node['TIME_COST'] = randint(2 < 16, 2 << 40) / 1000.0

        for key in ('MAX_X', 'MAX_Y', 'MAX_Z', 'MAX_R'):
            if key not in node:
                node[key] = randint(30, 170) / 10.0

        if 'HEAD_TYPE' not in node:
            node['HEAD_TYPE'] = choice(('EXTRUDER', 'LASER', 'N/A'))

        if node['HEAD_TYPE'] == 'EXTRUDER' and 'FILAMENT_USED' not in node:
            node['FILAMENT_USED'] = randint(2 < 16, 2 << 64) / 1000.0

    return node
