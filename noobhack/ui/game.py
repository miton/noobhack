import re
import curses 
import locale
import logging

from copy import deepcopy
from noobhack.ui.common import styles, colors, get_color

class Game:
    """
    Draw the game in the terminal.
    """

    def __init__(self, term):
        self.term = term
        self.old_display = deepcopy(self.term.display) #doesn't handle first frame properly
        self.old_attrib = deepcopy(self.term.attributes)
        self.code = locale.getpreferredencoding()

    def _redraw_row(self, window, row):
        """
        Draw a single game-row in the curses display window. This means writing
        the text from the in-memory terminal out and setting the color/style
        attributes appropriately.
        """
        #window.scrollok(True)
        row_c = self.term.display[row].encode(self.code)
        max_y, max_x = window.getmaxyx()
        #logging.debug("_redraw_row -- row:%d code:%r", row, row_c)       
        if row == max_y -1:
           window.addstr(row, 0, row_c[:-1])
           window.insch(row_c[-1])
        else:
           window.addstr(row, 0, row_c)

        row_a = self.term.attributes[row]
        for col, (char_style, foreground, background) in enumerate(row_a): 
            char_style = set(char_style)
            foreground = colors.get(foreground, -1)
            background = colors.get(background, -1)
            char_style = [styles.get(s, curses.A_NORMAL) for s in char_style]
            attrs = char_style + [get_color(foreground, background)]
            window.chgat(row, col, 1, reduce(lambda a, b: a | b, attrs)) 

        if "HP:" in row_c:
            # Highlight health depending on much much is left.
            match = re.search("HP:(\\d+)\\((\\d+)\\)", row_c)
            if match is not None:
                hp, hp_max = match.groups()
                ratio = float(hp) / float(hp_max)

                if ratio <= 0.25:
                    attrs = [curses.A_BOLD, get_color(curses.COLOR_WHITE, curses.COLOR_RED)]
                elif ratio <= 0.5:
                    attrs = [curses.A_BOLD, get_color(curses.COLOR_YELLOW)]
                else:
                    attrs = [curses.A_BOLD, get_color(curses.COLOR_GREEN)]
                attrs = reduce(lambda a, b: a | b, attrs)
                window.chgat(row, match.start() + 3, match.end() - match.start() - 3, attrs)


    def redraw(self, window):
        """
        Repaint the screen with the new contents of our terminal emulator...
        """

        #window.erase()
        for row_index in xrange(len(self.term.display)):
            redraw = False
            for col_index in xrange(len(self.term.display[row_index])):
                if self.term.display[row_index][col_index] != self.old_display[row_index][col_index] or self.term.attributes[row_index][col_index] != self.old_attrib[row_index][col_index]:
                   redraw = True
                   break
            if redraw:
               self._redraw_row(window, row_index)

        # Don't forget to move the cursor to where it is in game...
        cur_x, cur_y = self.term.cursor()
        window.move(cur_y, cur_x)

        # Finally, redraw the whole thing.
        window.noutrefresh()
        self.old_display = deepcopy(self.term.display)
        self.old_attrib = deepcopy(self.term.attributes)


