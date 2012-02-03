import os
import telnetlib
import logging

from struct import pack
from telnetlib import ECHO, SGA, TTYPE, NAWS, LINEMODE, IAC, DO, WILL, WONT, DONT, SB, SE, LFLOW, NEW_ENVIRON, STATUS, TSPEED, XDISPLOC

class Telnet:
    """
    Runs and manages the input/output of a remote nethack game. The class 
    implements a telnet client in as much as the python telnetlib makes that
    possible (grumble, grumble, grumble).
    """

    def __init__(self, host="nethack.alt.org", port=23, size=(80,24)):
        self.host = host
        self.port = port
        self.conn = None
        self.size = size

    def write(self, buf):
        """ Proxy input to the telnet process' stdin. """
        #self.conn.get_socket().sendall(buf)
        self.conn.write(buf)

    def read(self):
        """ 
        Proxy output from the telnet process' stdout. This shouldn't block 
        """
        try:
            return self.conn.read_very_eager()
        except EOFError, ex:
            # The telnet connection closed.
            raise IOError(ex)

    def open(self):
        """ Open a connection to a telnet server.  """

        self.conn = telnetlib.Telnet(self.host, self.port)
        self.conn.set_option_negotiation_callback(self.set_option)
        #self.conn.get_socket().sendall(pack("<ccccccccccccccccccccc", IAC, DO, SGA, IAC, WILL, TTYPE, IAC, WILL, NAWS, IAC, WILL, LFLOW, IAC, WILL, LINEMODE, IAC, WILL, NEW_ENVIRON, IAC, DO, STATUS))
        self.conn.get_socket().sendall(pack(">cccccccccccc", IAC, DO, SGA, IAC, WILL, TTYPE, IAC, WILL, NAWS, IAC, DO, STATUS))

    def close(self):
        """ Close the connection. """
        self.conn.close()

    def fileno(self):
        """ Return the fileno of the socket.  """
        return self.conn.get_socket().fileno()

    def set_option(self, socket, command, option):
        """ Configure our telnet options. This is magic. Don't touch it. """
	logging.debug("set_option cmd:%02X option:%02X, sbdataq:%r", ord(command), ord(option), self.conn.sbdataq)
        if command == telnetlib.DO and option == TTYPE:
            # Promise we'll sendall a terminal type
            socket.sendall("%s%s\x18" % (telnetlib.IAC, telnetlib.WILL))
        elif command == telnetlib.DO and option == ECHO:
            # Pinky swear we'll echo
#            socket.sendall("%s%s\x01" % (telnetlib.IAC, telnetlib.WILL))
	    logging.debug("server requested we echo, tell them no")
            socket.sendall(pack(">ccc", telnetlib.IAC, telnetlib.WONT, telnetlib.ECHO))
        elif command == telnetlib.DO and option == NAWS:
            # And we should probably tell the server we will sendall our window
            # size
            logging.debug("callback on option NAWS")
            #socket.sendall("%s%s\x1f" % (telnetlib.IAC, telnetlib.WILL))
            soft_pack = pack(">cccHHcc", telnetlib.IAC, telnetlib.SB, telnetlib.NAWS, self.size[1]-1, self.size[0], telnetlib.IAC, telnetlib.SE)
            logging.debug("soft_pack: %r size:%r", soft_pack, self.size)
            socket.sendall(soft_pack)
        elif command == telnetlib.DO and option == TSPEED:
            # Tell the server to sod off, we won't sendall the terminal speed
            socket.sendall("%s%s\x20" % (telnetlib.IAC, telnetlib.WONT))
        elif command == telnetlib.DO and option == XDISPLOC:
            socket.sendall("%s%s\x23" % (telnetlib.IAC, telnetlib.WONT))
            #socket.sendall(pack("<cccs
        elif command == telnetlib.DO and option == "\x27":
            # We will sendall the environment, though, since it might have nethack
            # specific options in it.
            socket.sendall("%s%s\x27" % (telnetlib.IAC, telnetlib.WILL))
        #elif self.conn.rawq.startswith("\xff\xfa\x27\x01\xff\xf0\xff\xfa"):
            # We're being asked for the environment settings that we promised
            # earlier
        elif command == SE and self.conn.sbdataq == '\x27\x01':
            logging.debug("sending environ")
            socket.sendall("%s%s\x27\x00%s%s%s" %
                        (telnetlib.IAC,
                         telnetlib.SB,
                         '\x00"NETHACKOPTIONS"\x01"%s"' % os.environ.get("NETHACKOPTIONS", ""),
                         telnetlib.IAC,
                         telnetlib.SE))
            # We're being asked for the terminal type that we promised earlier
        elif command == SE and self.conn.sbdataq == '\x18\x01':
            logging.debug("sending ttype")
            socket.sendall("%s%s\x18\x00%s%s%s" % 
                        (telnetlib.IAC,
                         telnetlib.SB,
                         "xterm-color",
                         telnetlib.IAC,
                         telnetlib.SE))
         
