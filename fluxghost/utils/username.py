import getpass


def get_username(fallback='user'):
    try:
        return getpass.getuser()
    except Exception:
        return fallback
