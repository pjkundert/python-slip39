import getpass
import logging
import sys

log_cfg				= {
    "level":	logging.WARNING,
    "datefmt":	'%Y-%m-%d %H:%M:%S',
    #"format":	'%(asctime)s.%(msecs).03d %(threadName)10.10s %(name)-16.16s %(levelname)-8.8s %(funcName)-10.10s %(message)s',
    "format":	'%(asctime)s %(name)-16.16s %(message)s',
}

log_levelmap 			= {
    -2: logging.FATAL,
    -1: logging.ERROR,
    0: logging.WARNING,
    1: logging.INFO,
    2: logging.DEBUG,
}


def log_level( adjust ):
    """Return a logging level corresponding to the +'ve/-'ve adjustment"""
    return log_levelmap[
        max(
            min(
                adjust,
                max( log_levelmap.keys() )
            ),
            min( log_levelmap.keys() )
        )
    ]


def ordinal(num):
    ordinal_dict		= {1: "st", 2: "nd", 3: "rd"}
    q, mod			= divmod( num, 10 )
    suffix			= q % 10 != 1 and ordinal_dict.get(mod) or "th"
    return f"{num}{suffix}"


def input_secure( prompt, secret=True ):
    """When getting secure (optionally secret) input from standard input, we don't want to use getpass, which
    attempts to read from /dev/tty.

    """
    if sys.stdin.isatty():
        # From TTY; provide prompts, and do not echo secret input
        if secret:
            return getpass.getpass( prompt )
        else:
            return input( prompt )
    else:
        # Not a TTY; don't litter pipeline output with prompts
        return input()
