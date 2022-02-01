import os
import logging
import pty
import threading

import pytest

try:
    from serial		import Serial
except ImportError:
    Serial			= None

from .api		import RANDOM_BYTES, accountgroups
from .generator		import chacha20poly1305, accountgroups_output, accountgroups_input


def listener(port):
    # continuously listen to commands on the master device
    while True:
        res = b""
        while not res.endswith(b"\r\n"):
            # keep reading one byte at a time until we have a full line
            res += os.read(port, 1)
        print("command: %s" % res)

        # write back the response
        if res == b'QPGS\r\n':
            os.write(port, b"correct result\r\n")
        else:
            os.write(port, b"I don't understand\r\n")


@pytest.mark.skipif( not Serial,
                     reason="Serial testing needs pyserial" )
def test_serial():
    """Start the testing"""
    master,slave = pty.openpty()		# open the pseudoterminal
    s_name = os.ttyname(slave)			# translate the slave fd to a filename

    logging.info( f"Pty name: {s_name}" )

    # create a separate thread that listens on the master device for commands
    thread = threading.Thread(target=listener, args=[master])
    thread.daemon = True
    thread.start()

    # open a pySerial connection to the slave.  Receiver can signal sender to stop/start
    ser = Serial(s_name, 2400, timeout=1)

    ser.write(b'test2\r\n')			# write the first command
    res = b""
    while not res.endswith(b'\r\n'):
        # read the response
        res += ser.read()
    print("result: %s" % res)
    assert res.startswith( b"I don't understand" )

    ser.write(b'QPGS\r\n')			# write a second command
    res = b""
    while not res.endswith(b'\r\n'):
        # read the response
        res += ser.read()
    print("result: %s" % res)
    assert res.startswith( b"correct result" )


def generator( password, cryptopaths, fd ):
    """Generate a sequence of Accounts to the given file descriptor."""
    fdout		= os.fdopen( fd, "w" )
    nonce		= RANDOM_BYTES( 12 )
    cipher		= chacha20poly1305( password=password )
    for index,group in enumerate( accountgroups(
        master_secret	= b'\xff' * 16,
        cryptopaths	= cryptopaths,
    )):
        logging.info( f"Sending: {group}" )
        accountgroups_output(
            group	= group,
            index	= index,
            cipher	= cipher,
            nonce	= nonce,
            corrupt	= .01,
            file	= fdout,
        )


@pytest.mark.skipif( not Serial,
                     reason="Serial testing needs pyserial" )
def test_groups_pty():
    password			= "password"
    master,slave		= pty.openpty()
    slave_name			= os.ttyname( slave )

    cryptopaths			= [
        ("ETH", "m/44'/60'/0'/0/-10"),
        ("ETH", "m/44'/ 0'/0'/0/-10"),
    ]

    gen				= threading.Thread(
        target	= generator,
        args	= [password, cryptopaths, master] )
    gen.daemon			= True
    gen.start()

    class SerialEOF( Serial ):
        """Convert any SerialException to an EOFError, for compatibility with PTY.  In real serial
        ports, we'll handle detection of counterparty readiness with DTR/DSR, and flow control with
        RTS/CTS.

        """
        def read( self, size=1 ):
            while True:
                try:
                    return super( SerialEOF, self ).read( size=size )
                except Exception as exc:  # SerialError as exc:
                    # if "readiness" in str(exc):
                    #     time.sleep( .1 )
                    #     continue
                    raise EOFError( str( exc ))

    ser				= SerialEOF( slave_name, timeout=1)
    for group in accountgroups_input(
        cipher		= chacha20poly1305( password=password ),
        encoding	= 'UTF-8',
        file		= ser
    ):
        logging.info( f"Receive: {group}" )


# def transmitter():


#     yield from addresses(
#         master_secret			= b"\xFF" * 16,
#         paths


# def test_serial_xonxoff():
#     """Ensure that flow-control works.  The idealy secure solution is to use hardware RTS/CTS flow
#     control, with no tx circuit.  However, even a regular serial link with software XON/XOFF flow
#     control is much more secure than a network-connected peer."""
