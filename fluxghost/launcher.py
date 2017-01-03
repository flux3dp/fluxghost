
import logging.config
import logging
import sys

from fluxclient.utils.version import StrictVersion


def check_fluxclient():
    from fluxclient import __version__ as v
    sys.modules.pop("fluxclient")
    lower_bound = '1.2.3'
    upper_bound = '2.0a1'
    if StrictVersion(v) < StrictVersion(lower_bound):
        raise RuntimeError(
            "Your fluxclient need to update (>={})".format(lower_bound))
    if StrictVersion(v) >= StrictVersion(upper_bound):
        raise RuntimeError("fluxclient is too new (<{})".format(upper_bound))


def setup_logger(options):
    log_datefmt = "%Y-%m-%d %H:%M:%S"
    log_format = "[%(asctime)s,%(levelname)s,%(name)s] %(message)s"

    log_level = logging.DEBUG if options.debug else logging.INFO

    handlers = {}
    # if sys.stdout.isatty():
    handlers['console'] = {
        'level': log_level,
        'formatter': 'default',
        'class': 'logging.StreamHandler',
    }

    if options.logfile:
        handlers['file'] = {
            'level': log_level,
            'formatter': 'default',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': options.logfile,
            'maxBytes': 5 * (1 << 20),  # 10M
            'backupCount': 1
        }

    if options.sentry:
        handlers['sentry'] = {
            'level': 'ERROR',
            'class': 'raven.handlers.logging.SentryHandler',
            'dsn': options.sentry,
        }

    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': True,
        'formatters': {
            'default': {
                'format': log_format,
                'datefmt': log_datefmt
            }
        },
        'handlers': handlers,
        'loggers': {},
        'root': {
            'handlers': list(handlers.keys()),
            'level': 'DEBUG',
            'propagate': True
        }
    })


def setup_env(options):
    check_fluxclient()
    setup_logger(options)


def show_version(verbose):
    from fluxghost import __version__ as gfv
    print("fluxghost %s" % gfv)
    from fluxclient import __version__ as cfv
    print("fluxclient %s" % cfv)
