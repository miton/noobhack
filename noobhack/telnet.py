import os
import telnetlib
import logging

class Telnet:
    """
    Runs and manages the input/output of a remote nethack game. The class 
    implements a telnet client in as much as the python telnetlib makes that
    possible (grumble, grumble, grumble).
    """

    def __init__(self, host="nethack.alt.org", port=23):
        self.host = host
        self.port = port
        self.conn = None

    def write(self, buf):
        """ Proxy input to the telnet process' stdin. """
        self.conn.get_socket().sendall(buf)

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

    def close(self):
        """ Close the connection. """
        self.conn.close()

    def fileno(self):
        """ Return the fileno of the socket.  """
        return self.conn.get_socket().fileno()

    def set_option(self, socket, command, option):
        """ Configure our telnet options. This is magic. Don't touch it. """

        if command == telnetlib.DO and option == "\x18":
            # Promise we'll sendall a terminal type
            socket.sendall("%s%s\x18" % (telnetlib.IAC, telnetlib.WILL))
        elif command == telnetlib.DO and option == "\x01":
            # Pinky swear we'll echo
            socket.sendall("%s%s\x01" % (telnetlib.IAC, telnetlib.WILL))
        elif command == telnetlib.DO and option == "\x1f":
            # And we should probably tell the server we will sendall our window
            # size
            logging.debug("callback on option NAWS")
            socket.sendall("%s%s\x1f" % (telnetlib.IAC, telnetlib.WILL))
            #socket.sendall("%s%s\x1f\x00\x96\x00\x1E%s%s" % (telnetlib.IAC, telnetlib.SB, telnetlib.IAC, telnetlib.SE))
        elif command == telnetlib.DO and option == "\x20":
            # Tell the server to sod off, we won't sendall the terminal speed
            socket.sendall("%s%s\x20" % (telnetlib.IAC, telnetlib.WONT))
        elif command == telnetlib.DO and option == "\x23":
            # Tell the server to sod off, we won't sendall an x-display terminal
            socket.sendall("%s%s\x23" % (telnetlib.IAC, telnetlib.WONT))
        elif command == telnetlib.DO and option == "\x27":
            # We will sendall the environment, though, since it might have nethack
            # specific options in it.
            socket.sendall("%s%s\x27" % (telnetlib.IAC, telnetlib.WILL))
        elif self.conn.rawq.startswith("\xff\xfa\x27\x01\xff\xf0\xff\xfa"):
            # We're being asked for the environment settings that we promised
            # earlier
            socket.sendall("%s%s\x27\x00%s%s%s" %
                        (telnetlib.IAC,
                         telnetlib.SB,
                         '\x00"NETHACKOPTIONS"\x01"%s"' % os.environ.get("NETHACKOPTIONS", ""),
                         telnetlib.IAC,
                         telnetlib.SE))
            # We're being asked for the terminal type that we promised earlier
            socket.sendall("%s%s\x18\x00%s%s%s" % 
                        (telnetlib.IAC,
                         telnetlib.SB,
                         "xterm-color",
                         telnetlib.IAC,
                         telnetlib.SE))
