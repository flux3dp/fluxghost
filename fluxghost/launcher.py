import logging
import logging.config
import sys


def setup_logger(options=None):
    log_datefmt = '%Y-%m-%d %H:%M:%S'
    log_format = '[%(asctime)s,%(levelname)s,%(name)s] %(message)s'

    log_level = logging.DEBUG if getattr(options, 'debug', False) else logging.INFO

    handlers = {}
    # if sys.stdout.isatty():
    handlers['console'] = {
        'level': log_level,
        'formatter': 'default',
        'class': 'logging.StreamHandler',
    }

    if getattr(options, 'logfile', False):
        handlers['file'] = {
            'level': log_level,
            'formatter': 'default',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': options.logfile,
            'maxBytes': 5 * (1 << 20),  # 10M
            'backupCount': 1,
        }

    if getattr(options, 'sentry', False):
        handlers['sentry'] = {
            'level': 'ERROR',
            'class': 'raven.handlers.logging.SentryHandler',
            'dsn': options.sentry,
        }

    logging.config.dictConfig(
        {
            'version': 1,
            'disable_existing_loggers': True,
            'formatters': {'default': {'format': log_format, 'datefmt': log_datefmt}},
            'handlers': handlers,
            'loggers': {},
            'root': {'handlers': list(handlers.keys()), 'level': 'DEBUG', 'propagate': True},
        }
    )


def setup_env(options):
    setup_logger(options)


def show_version(verbose):
    from fluxghost import __version__ as gfv

    print('fluxghost %s' % gfv)
    from fluxclient import __version__ as cfv

    print('fluxclient %s' % cfv)
