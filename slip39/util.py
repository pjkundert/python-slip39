import logging

log_cfg				= {
    "level":	logging.WARNING,
    "datefmt":	'%Y-%m-%d %H:%M:%S',
    #"format":	'%(asctime)s.%(msecs).03d %(threadName)10.10s %(name)-16.16s %(levelname)-8.8s %(funcName)-10.10s %(message)s',
    "format":	'%(asctime)s %(name)-16.16s %(message)s',
}


def ordinal(num):
    ordinal_dict		= {1: "st", 2: "nd", 3: "rd"}
    q, mod			= divmod( num, 10 )
    suffix			= q % 10 != 1 and ordinal_dict.get(mod) or "th"
    return f"{num}{suffix}"
