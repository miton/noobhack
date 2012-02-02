#!/usr/bin/env python -u

import os
import re
import sys
import select
import curses
import locale
import optparse 

import cPickle as pickle

import vt102 
import logging
import telnetlib
from struct import pack

from time import time,sleep 
from noobhack import telnet, process, proxy
from noobhack.game import player, dungeon, brain, farmer

from noobhack.ui.game import *
from noobhack.ui.helper import *
from noobhack.ui.minimap import *
from noobhack.ui.common import *

def get_parser():
    parser = optparse.OptionParser(
        description="noobhack helps you ascend playing nethack."
    )

    parser.set_defaults(
        local=True, 
        port=23,
        help=False,
        encoding="ascii",
        crumbs=False
    )

    parser.remove_option("-h")

    parser.add_option("--help",
                      help="show this message and exit",
                      action="store_true",
                      dest="help")

    parser.add_option("-l", 
                      "--local", 
                      help="play a local game [default: %default]", 
                      action="store_true", 
                      dest="local")

    parser.add_option("-h", 
                      "--host", 
                      help="play a remote game on HOST", 
                      type="string",
                      dest="host")

    parser.add_option("-p", 
                      "--port", 
                      help="connect to the remote host on PORT [default: %default]", 
                      type="int",
                      dest="port")

    parser.add_option("-s", 
                      "--save", 
                      help="use a specific save file label (if playing multiple games)", 
                      type="string",
                      metavar="NAME",
                      dest="save")

    parser.add_option("--crumbs", 
                      help="display breadcrumbs when the helper overlay is on screen",
                      action="store_true",
                      dest="crumbs")
    
    parser.add_option("-e", 
                      "--encoding",
                      help="set the terminal emulator to ENC [default: %default]",
                      type="string", 
                      metavar="ENC",
                      dest="encoding")

    parser.add_option("-d",
                      "--debug",
                      help="start the game in debug mode",
                      action="store_true",
                      dest="debug")

    return parser


def parse_options():
    """
    Parse commandline options and return a dict with any settings.
    """

    parser = get_parser()
    (options, args) = parser.parse_args()

    if options.host is not None:
        options.local = False

    if options.help:
        get_parser().print_help()
        sys.exit(1)

    return options

class Noobhack:
    """
    Manager of the global game state. This runs the main event loop and makes 
    sure the screen gets updated as necessary.
    """

    noobhack_dir = os.path.expanduser("~/.noobhack")

    def __init__(self, toggle_help="\t", toggle_map="`"):
        self.options = parse_options()

        if self.options.save:
            self.save_file = os.path.join(self.noobhack_dir, "save-%s" % self.options.save)
        else:
            self.save_file = os.path.join(self.noobhack_dir, "save")

        self.toggle_help = toggle_help
        self.toggle_map = toggle_map
        self.mode = "game"
        self.playing = False
        self.reloading = False

	self.naws_last_sent = time()
        self.last_input = time()
        self.pending_input = []

	if not os.path.exists(self.noobhack_dir):
            os.makedirs(self.noobhack_dir, 0755)

        self.nethack = self.connect_to_game() 
        self.output_proxy = proxy.Output(self.nethack)
        self.input_proxy = proxy.Input(self.nethack) 

        # Create an in-memory terminal screen and register it's stream
        # processor with the output proxy.
        self.stream = vt102.stream()

        # For some reason that I can't assertain: curses freaks out and crashes
        # when you use exactly the number of rows that are available on the
        # terminal. It seems easiest just to subtract one from the rows and 
        # deal with it rather than hunt forever trying to figure out what I'm
        # doing wrong with curses.
        rows, cols = size()
        self.term = vt102.screen((rows-1, cols), self.options.encoding)
        self.term.attach(self.stream)
        
        if not self.options.local:
            packet = pack(">BBBHHBB", 255, 250, 31, cols, rows-1, 255, 240)
            self.nethack.conn.get_socket().send(packet)
            logging.debug("sent NAWS on connect: %s", ' '.join(['%02x' % ord(c) for c in packet]))

        self.output_proxy.register(self.stream.process)

	
        self.game = Game(self.term)

        self.output_proxy.register(self._restore_game_checker)
        self.output_proxy.register(self._game_started_checker)
        self.output_proxy.register(self._quit_or_died_checker)
        
        # Register the `toggle` key to open up the interactive nooback 
        # assistant.
        self.input_proxy.register(self._toggle)

    def _quit_or_died_checker(self, data):
        """
        Check to see if the player quit or died. In either case, we need to
        delete our, now pointless, save file.
        """

        match = re.search("Do you want your possessions identified\\?", data)
        if match is not None:
            self.delete()
            self.playing = False
            self.output_proxy.unregister(self._quit_or_died_checker)

    def _start(self):
        if self.reloading:
            self.player, self.dungeon = self.load()
        else:
            self.player, self.dungeon = player.Player(), dungeon.Dungeon() 

        self.player.listen()
        self.dungeon.listen()

        self.brain = brain.Brain(self.term, self.output_proxy, self.input_proxy)
        self.helper = Helper(self.brain, self.player, self.dungeon)
        self.minimap = Minimap()
        self.farmer = farmer.Farmer(self.pending_input)
        self.farmer.listen()

    def _game_started_checker(self, data):
        """
        Check to see if the game is playing or not.
        """
        match = re.search("welcome( back)? to NetHack!", data)
        if match is not None:
            self.playing = True
            self._start()
            self.output_proxy.unregister(self._game_started_checker)

    def _restore_game_checker(self, data):
        match = re.search("Restoring save file...", data)
        if match is not None:
            self.reloading = True
            self.output_proxy.unregister(self._restore_game_checker)

    def load(self):
        if os.path.exists(self.save_file):
            save_file = open(self.save_file, "r")
            try:
                return pickle.load(save_file)
            finally:
                save_file.close()
        elif self.options.debug:
            return player.Player(), dungeon.Dungeon() 
        else:
	    return player.Player(), dungeon.Dungeon()
            """ 
            raise RuntimeError(
                "NetHack is trying to restore a game file, but noobhack " + 
                "doesn't have any memory of this game. While noobhack will " +
                "still work on a game it doesn't know anything about, there " +
                "will probably be errors. If you'd like to use noobhack, " +
                "run nethack and quit your current game, then restart " + 
                "noobhack."
            )
	   """

    def save(self):
        save_file = open(self.save_file, "w")
        try:
            pickle.dump((self.player, self.dungeon), save_file)
        finally:
            save_file.close()

    def delete(self):
        if os.path.exists(self.save_file):
            os.remove(self.save_file)

    def connect_to_game(self):
        """
        Fork the game, or connect to a foreign host to play.

        :return: A file like object of the game. Reading/writing is the same as
        accessing stdout/stdin in the game respectively.
        """

        try:
            if self.options.local:
                conn = process.Local(self.options.debug)
            else:
                conn = telnet.Telnet(
                    self.options.host,
                    self.options.port
                )
            conn.open()
        except IOError, error:
            sys.stderr.write("Unable to open nethack: `%s'\n" % error)
            raise 

        return conn

    def _toggle(self, key):
        """
        Toggle between game mode and help mode.
        """

        if key == self.toggle_help:
            if self.mode == "game":
                self.mode = "help"
            else:
                self.mode = "game"
            return False
        elif key == self.toggle_map:
            if self.mode == "bot":
               self.mode = "game"
               return False
            else:
               self.mode = "bot"
               del self.pending_input[:]
               self.farmer.abort = False
               return False
        elif key == "!":
            self.mode = "debug"
            return False
    def _game(self, window):
        """
        Run the game loop.
        """

        #if self.mode == "map":
            #self.minimap.display(self.dungeon.graph, window, self.toggle_map)
            # Map mode handles it's own input. Make sure that we don't get
            # forever stuck in map mode by toggling back out of it when it's
            # done.
        #    self.mode = "game"

        self.game.redraw(window)
        if self.mode == "help":
            self.helper.redraw(window, self.options.crumbs)

        window.refresh()

        if self.playing:
            self.save()
        else:
           #just spam NAWS to figure out wtf is going on
           if time() > self.naws_last_sent + .2:
              rows,cols = size()
              packet = pack(">BBBHHBB", 255, 250, 31, cols, rows-1, 255, 240)
              self.nethack.conn.get_socket().send(packet)
              logging.debug("sent NAWS on connect: %s", ' '.join(['%02x' % ord(c) for c in packet]))
              self.naws_last_sent = time()


        wait_time = .1
        # Let's wait until we have something to do...
        #logging.debug("%f %s", time(), self.pending_input) 
        #NB: I don't understand how this works when we make up input since chances are it should just be blocked on the select?
        #also is the eating first input my fault or somewhere else
	if len(self.pending_input) > 0 and time() > self.last_input + wait_time and self.mode == 'bot' and not self.farmer.abort:
	    first = self.pending_input.pop(0)
            self.input_proxy.game.write(first)
	    logging.debug("sending %s, left: %s", first, self.pending_input)
#            self.pending_input = self.pending_input[1:]
            self.last_input = time()

        if len(self.pending_input) > 0 and self.mode == 'bot':
           available = select.select(
            [self.nethack.fileno(), sys.stdin.fileno()], [], []
           ,wait_time / 2.0)[0]
        else:
           available = select.select(
            [self.nethack.fileno(), sys.stdin.fileno()], [], []
           )[0]

	
        if sys.stdin.fileno() in available:
            # Do our input logic.
            self.input_proxy.proxy()

        if self.nethack.fileno() in available:
            # Do our display logic.
            self.output_proxy.proxy()

    def run(self, window):
        """
        Game loop.
        """

        # We prefer to let the console pick the colors for the bg/fg instead of
        # using what curses thinks looks good.
        curses.use_default_colors()

        while True:
            self._game(window)

if __name__ == "__main__":
    locale.setlocale(locale.LC_ALL, "")
    
    logging.basicConfig(filename="noobhack.log",level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

    logging.debug("started noobhack")

    hack = Noobhack()
    try:
        curses.wrapper(hack.run)
    except process.ProcError, e:
        pid, exit = os.wait()
        sys.stdout.write(e.stdout.read())
    except IOError, e:
        print e
