def get_grid(version):
    if version == 'v2':
        return (
            [0, 10] + [x for x in range(20, 411, 30)] + [420, 430],
            [0, 10, 20] + [y for y in range(30, 301, 30)],
        )
    raise ValueError('Invalid version')
