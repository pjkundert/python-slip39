import os
import logging
import pty
import threading

from serial		import Serial

#from .generate 		import addresses


def listener(port):
    # continuously listen to commands on the master device
    while 1:
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


# def transmitter():
#     """Sends an unending sequence of "path address ... \n", using software/hardware flow control to
#     limit output.

#     """
#     yield from addresses(
#         master_secret			= b"\xFF" * 16,
#         paths


# def test_serial_xonxoff():
#     """Ensure that flow-control works.  The idealy secure solution is to use hardware RTS/CTS flow
#     control, with no tx circuit.  However, even a regular serial link with software XON/XOFF flow
#     control is much more secure than a network-connected peer."""
