import logging

from pathlib		import Path

#from . import limits


log				= logging.getLogger( "limits_test" )


def test_authorize( tmp_path ):
    test			= Path( __file__ ).resolve()
    here			= Path( tmp_path ).resolve()

    log.info( f"authorizing: {test}, {here}" )
