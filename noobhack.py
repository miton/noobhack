#!/usr/bin/env python -u

import os
import re
import sys
import select
import socket
import curses
import locale
import optparse 

import cPickle as pickle
import cProfile 
import vt102 
import logging
import telnetlib

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

    def __init__(self, conn, toggle_help="\t", toggle_map="`"):
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

        self.last_input = time()
        self.pending_input = []

        self.input_socket = conn

	if not os.path.exists(self.noobhack_dir):
            os.makedirs(self.noobhack_dir, 0755)

        self.nethack = self.connect_to_game() 
        self.output_proxy = proxy.Output(self.nethack, self.input_socket)
        self.input_proxy = proxy.Input(self.input_socket, self.nethack) 

        # Create an in-memory terminal screen and register it's stream
        # processor with the output proxy.
        self.stream = vt102.stream()

        # For some reason that I can't assertain: curses freaks out and crashes
        # when you use exactly the number of rows that are available on the
        # terminal. It seems easiest just to subtract one from the rows and 
        # deal with it rather than hunt forever trying to figure out what I'm
        # doing wrong with curses.
        rows, cols = size()
        self.term = vt102.screen((rows, cols), self.options.encoding)
        self.term.attach(self.stream)
        
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
            conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            logging.debug("connecting to NAO")
            conn.connect(('nethack.alt.org', 23))
            logging.debug("connected to NAO")
            
        except IOError, error:
            logging.error("Unable to open nethack: `%s'\n" % error)
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


        if self.playing:
            self.save()

        wait_time = .1 
        #logging.debug("%f %s", time(), self.pending_input) 
        #NB: I don't understand how this works when we make up input since chances are it should just be blocked on the select?

        before_select = time()
        if len(self.pending_input) > 0 and self.mode == 'bot':
           available,w,e = select.select(
            [self.nethack, self.input_socket], [], []
           ,wait_time / 2.0)
        else:
           available,w,e = select.select(
            [self.nethack, self.input_socket], [], []
           )
        logging.debug("select timediff: %s", time() - before_select)
	
        if len(e) > 0:
           loggging.debug("error on socket")
           return False

        if self.input_socket in available:
            # Do our input logic.
            if not self.input_proxy.proxy():
               return False

        if self.nethack in available:
            # Do our display logic.
            if not self.output_proxy.proxy():
               return False
        
        if len(self.pending_input) > 0 and time() > self.last_input + wait_time and self.mode == 'bot' and not self.farmer.abort:
            first = self.pending_input.pop(0)
            #self.input_proxy.game.write(first)
            self.nethack.send(first)
            logging.debug("sending %s, left: %s", first, self.pending_input)
            self.last_input = time()


    def run(self, window):
        """
        Game loop.
        """

        # We prefer to let the console pick the colors for the bg/fg instead of
        # using what curses thinks looks good.
#        curses.use_default_colors()

        while self._game(window):
           pass

if __name__ == "__main__":
    locale.setlocale(locale.LC_ALL, "")
    
    logging.basicConfig(filename="noobhack.log",level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

    try:
        #curses.wrapper(hack.run)
        #cProfile.run("curses.wrapper(hack.run)",'profile')
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(('', 2000))
        while True:
          listener.listen(1)
          conn, addr = listener.accept()
          logging.debug("connection from %s", addr)
          hack = Noobhack(conn)
          hack.run(None)
    except process.ProcError, e:
        pid, exit = os.wait()
        sys.stdout.write(e.stdout.read())
    except IOError, e:
        print e
