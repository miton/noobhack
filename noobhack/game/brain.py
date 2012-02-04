"""
The brain manages events from the game. Other classes are responsible for 
consuming and processing those events in an intelligent way.
"""

import re
import logging

from noobhack.game.graphics import ibm
from noobhack.game import shops, status, intrinsics, sounds, dungeon, farmer
from noobhack.game.events import dispatcher as event

class Brain:
    """
    GrraaAAaaaAaaaa... braaaAAaaains...
    """

    def __init__(self, term, output_proxy, input_proxy):
        self.term = term
        output_proxy.register(self.process)
        # TODO: Fix branchporting. Disable for now, though, since there's a
        # perf overhead for callbacks.
        #input_proxy.register(self.monitor)

        self.last_move = None
        self.turn = 0
        self.dlvl = 0
        self.prev_cursor = (0, 0)

        self.hp = None
        self.seen_teleport = False
        self.hungry = False
        self.menu_type_clear = False
        self.menu_type = None

    def charisma(self):
        """ Return the player's current charisma """
        line = self._content()[-2]
        match = re.search("Ch:(\\d+)", line)
        if match is not None:
            return int(match.groups()[0])
        return None

    def sucker(self):
        """ 
        Return whether or not the player is considered a 'sucker'. A level 14 or lower tourists or anyone wearing a shirt with no armor or cloak over it. Confers a 33% penalty to the price of an object. Necessary when price identifying.
        """
        return False

    def _dispatch_level_feature_events(self, data):
        match = re.search("There is an altar to .* \\((\\w+)\\) here.", data)
        if match is not None:
            event.dispatch("level-feature", "altar (%s)" % match.groups()[0])

        match = re.search("a (large box)|(chest).", data)
        if match is not None:
            event.dispatch("level-feature", "chest")

        for feature, messages in sounds.messages.iteritems():
            for message in messages:
                match = re.search(message, data, re.I | re.M)
                if match is not None:
                    event.dispatch("level-feature", feature)

    def _dispatch_intrinsic_events(self, data):
        for name, messages in intrinsics.messages.iteritems():
            for message, value in messages.iteritems():
                match = re.search(message, data, re.I | re.M)
                if match is not None:
                    event.dispatch("intrinsic", name, value)

    def _dispatch_status_events(self, data):
        """
        Check the output stream for any messages that might indicate a status
        change event. If such a message is found, then dispatch a status event
        with the name of the status and it's value (either True or False).
        """

        for name, messages in status.messages.iteritems():
            for message, value in messages.iteritems():
                match = re.search(message, data, re.I | re.M)
                if match is not None:
                    event.dispatch("status", name, value)

    def _dispatch_kill_events(self, data):
         match = re.search(r"You kill (?:the )?([^!]+?)!", data)
         if match is not None:
             event.dispatch("kill", match.group(1))

    def _dispatch_altar_events(self, data):
         match = re.search("There is an altar to", data)
         if match is not None:
             event.dispatch("on_altar")

    def _dispatch_sacrifice_prompt_event(self, data):
         match = re.search(r"There (?:is a|are \d+) (.*?)(?: named (.*?))? here; sacrifice (?:it|one)\?", data)
         if match is not None:
             event.dispatch("sacrifice_prompt", match.groups())
         match = re.search(r"What do you want to sacrifice\? \[(.+?) or \?\*\]", data)
         if match is not None:
             event.dispatch("sacrifice_prompt_inv", match.group(1)) 
     
    def _dispatch_sacrifice_response_event(self, data):
         match = re.search(r"(Nothing happens|An object appears at your feet|[^\s]+ seems (?:slightly )mollified|You feel partially absolved|You glimpse a four-leaf clover at your feet|You have a hopeful feeling|You have a feeling of reconciliation)", data)
         if match is not None:
             event.dispatch("sacrifice_response", match.group(1))

    def _dispatch_eat_prompt_event(self, data):
         match = re.search("There (?:is a|are \d+) (.*?) here; eat (?:it|one)?", data)
         if match is not None:
              event.dispatch("eat_prompt", match.group(1))
         match = re.search(r"What do you want to eat\? (\[(.+?) or \?\*\])?", data)
         if match is not None:
              event.dispatch("eat_prompt_inv", match.group(1))

    def _dispatch_name_prompt_event(self, data):
         match = re.search(r"What do you want to call (.+?)\?", data)
         if match is not None:
              event.dispatch("name_prompt", match.group(1))

    def _dispatch_wield_prompt_event(self, data):
         match = re.search(r"What do you want to wield\? \[- (.*?) or \?\*\]", data)
         if match is not None:
              event.dispatch("wield_prompt", match.group(1))

    def _dispatch_item_pickup_events(self, data):
         for match in re.finditer(r"(.) - ([^.]+?)\.", data):
              event.dispatch("item_pickup", match.group(1), match.group(2))

    def _dispatch_i_see_no_monster_event(self, data):
        match = re.search("I see no monster there", data)
        if match:
            event.dispatch("see_no_monster")
    
    def _dispatch_unknown_direction_event(self, data):
        match = re.search('Unknown direction:', data)
        if match:
            event.dispatch("unknown_direction")

    #covered with the basic menu one
    #def _dispatch_loot_event(self, data):
    #    match = re.search('Loot which containers?', data)
    #    if match:

    
    def _dispatch_loot_do_what(self, data):
        match = re.search(r"((?:The (.*?) is empty.)? Do what\?)", data)
        if match:
           event.dispatch("loot_do_what")

    #def _dispatch_put_in_event(self, data):
    #    match = re.search('Put in what?', data)

    #def _dispatch_cast_spell_event(self, data):

    def _content(self):
        return [line.translate(ibm) for line 
                in self.term.display 
                if len(line.strip()) > 0]

    def _get_last_line(self):
        # The last line in the display is the one that contains the turn
        # information.
        for i in xrange(len(self.term.display)-1, -1, -1):
            line = self.term.display[i].translate(ibm).strip()
            if len(line) > 0:
                break
        return line

    def _get_first_line(self):
        return self.term.display[0].translate(ibm).strip()

    def _dispatch_branch_change_event(self):
        level = [line.translate(ibm) for line in self.term.display]
        if 6 <= self.dlvl <= 10 and dungeon.looks_like_sokoban(level):
            # If the player arrived at a level that looks like sokoban, she's 
            # definitely in sokoban.
            event.dispatch("branch-change", "sokoban")
        elif self.last_move == "down" and 3 <= self.dlvl <= 6 and \
           dungeon.looks_like_mines(level): 
            # The only entrace to the mines is between levels 3 and 5 and
            # the player has to have been traveling down to get there. Also
            # count it if the dlvl didn't change, because it *might* take
            # a couple turns to identify the mines. Sokoban, by it's nature
            # however is instantly identifiable. 
            event.dispatch("branch-change", "mines")

    def _dispatch_level_change_event(self):
        line = self._get_last_line()
        match = re.search("Dlvl:(\\d+)", line)
        if match is not None:
            dlvl = int(match.groups()[0])
            if dlvl != self.dlvl:
                if dlvl < self.dlvl:
                    self.last_move = "up"
                elif dlvl > self.dlvl:
                    self.last_move = "down"

                self.dlvl = dlvl
                event.dispatch(
                    "level-change", dlvl, 
                    self.prev_cursor, self.term.cursor()
                )
                return 

        # Couldn't find the dlvl line... this means we're somewhere outside
        # of the dungeon. Either in the end game, ft. ludios or in your quest.
        match = re.search("Home (\\d+)", line)
        if match is not None:
            dlvl = int(match.groups()[0])
            self.dlvl = dlvl + self.dlvl - 1
            if dlvl == 1:
                event.dispatch("branch-port", "quest")
            else:
                event.dispatch(
                    "level-change", self.dlvl, 
                    self.prev_cursor, self.term.cursor()
                )
            return 

        match = re.search("Fort Ludios", line)
        if match is not None:
            event.dispatch("branch-port", "ludios")
            return

    def _dispatch_level_teleport_event(self, data):
        for message in dungeon.messages["level-teleport"]:
            match = re.search(message, data)
            if match is not None:
                event.dispatch("level-teleport")

    def _dispatch_trap_door_event(self, data):
        for message in dungeon.messages["trap-door"]:
            match = re.search(message, data)
            if match is not None:
                event.dispatch("trap-door")

    def _dispatch_turn_change_event(self):
        """
        Dispatch an even each time a turn advances.
        """

        line = self._get_last_line()
        match = re.search("T:(\\d+)", line)
        if match is not None:
            turn = int(match.groups()[0])
            if turn != self.turn:
                self.turn = turn
                event.dispatch("turn", self.turn)

    def _dispatch_hp_change_event(self):
        line = self._get_last_line()
        match = re.search(r"HP:(\d+)", line)
        if match is not None:
           hp = int(match.group(1))
           if hp != self.hp:
              self.hp = hp
              event.dispatch("hp_change", hp)
    
    def _dispatch_stoning_event(self, data):
        match = re.search(r"(?:(?:You are slowing down)|(?:Your limbs are stiffening))", data)
        if match:
           event.dispatch('stoning')

    def _dispatch_life_saved_event(self, data):
        match = re.search(r"You die\.", data)
        if match:
           event.dispatch("died")

    def _dispatch_hunger_event(self):
        #XXX: findall
        line = self._get_last_line()
        match = re.search("(Hungry|Weak|Fainting|FoodPois|Fainted|Ill|Stun|Conf)", line)
        if match is not None:
           hunger = match.group(1)
           if self.hungry != hunger:
              self.hungry = hunger
              event.dispatch("hunger", hunger)
        elif self.hungry:
             self.hungry = False
             event.dispatch("unhungry")
    
    def _dispatch_burden_event(self):
        line = self._get_last_line()
        match = re.search("(Burdened|Stressed|Strained|Overtaxed)", line)
        if match is not None:
           burden = match.group(1)
           event.dispatch("burden", burden)

    statusline_re = re.compile("(Hungry|Weak)...")
    def _dispatch_statusline_events(self):
        line = self._get_last_line()
        
    def _dispatch_shop_entered_event(self, data):
        match = re.search(shops.entrance, data, re.I | re.M)
        if match is not None:
            shop_type = match.groups()[1]
            for t, _ in shops.types.iteritems():
                match = re.search(t, shop_type, re.I)
                if match is not None:
                    event.dispatch("shop-type", t)

    def _dispatch_move_event(self):
        if self.cursor_is_on_player():
            event.dispatch("move", self.term.cursor())

    def _dispatch_teleport_prompt_event(self, data):
        match = re.search("To what position do you want to be teleported\?", data)
        if match: 
           event.dispatch("teleport_prompt")
           self.seen_teleport = True

    def _dispatch_select_prompt_event(self, data):
        match = re.search(r"\(For instructions type a \?\)", data)
        if match and not self.seen_teleport:
           event.dispatch("select_name_prompt")
        else:
           self.seen_teleport = False

    def _dispatch_name_what_prompt_event(self,data):
        match = re.search("What do you wish to name\?", data)
        if match:
           event.dispatch("name_what")

    def _dispatch_extended_command_prompt_event(self):
        if self.term.display[0][0] == '#' and self.term.cursor() == (2,0):
           event.dispatch('extended_command_prompt')

#    def _dispatch_inventory_list_event(self, data):
#	#line = self._get_last_line()
#        match = re.search("\((?:\d+ of \d+|end)\)", data)
#        if match:
#           if self.menu_type is None:
#              for m in re.finditer(r"(.) - (.+?)(?:$|\x1b\[\d+;\d+(?:H|f))", data):
#                  event.dispatch('inventory_item', m.group(1), m.group(2))
          #elif self #dunno
   #taken over by generic menu_event 
   # def _dispatch_identify_list_event(self, data):
   #     match = re.search(r"What would you like to identify first\?", data)
   #     if match:
   #        self.menu_type = 'identify'
   #        for m in re.finditer(r"(.) - (.+?)$", data):
   #            event.dispatch('identify_item', m.group(1), m.group(2))
        
    def _dispatch_identify_done_event(self, data):
        match = re.search(r"You have already identified all of your possessions\.|That was all\.", data)
        if match:
           event.dispatch('identify_done')

    #def _dispatch_put_in_what_type_event(self,data):
    #    match = re.search("Put in what type of objects\?", data)
    #    if match:
    #       event.dispatch('put_in_type')
    #       #do I ever need the types when I can just do all? lazy for now
  
    def _dispatch_menu_events(self, data):
        menu_type_match = re.search(r"((?:What would you like to identify first\?)|(?:Loot which containers\?)|(?:Choose which spell to cast)|(?:Put in what type of objects\?)|(?:(?:The (.+?) is empty. )?Do what\?))", data) #What would you like to drop? -- but would make the next part not work
        t = {'W':'identify', 'L':'loot', 'C':'spell', 'P':'put_in', 'T':'loot_do_what', 'D':'loot_do_what'}
        if menu_type_match:
           self.menu_type = t[menu_type_match.group(1)[0]]
        elif self.menu_type is None:
           self.menu_type = 'inventory'
#        line = self._get_last_line()
        #actually end is only on single pages, so I don't need to fire this event at all
        #or do I after all if I use this for all pages
        #match = re.search(r"\((?:(\d+) of (\d+)|end))\)", line)
        match = re.search(r"\((?:(?:(\d+) of (\d+))|end)\)", data)
        if match:
           if self.menu_type in ['loot', 'drop', 'inventory','lootlist']:
              for m in re.finditer(r"(.) - (.+?)(?:$|\x1b\[\d+;\d+(?:H|f))", data):
                  event.dispatch(self.menu_type+'_item', m.group(1), m.group(2))
           elif self.menu_type in ['spell']:
             for m in re.finditer(r"(.) - (.*?)\s* (\d\*?)\s*([^\s]+)\s*(\d+)%", data):
                  event.dispatch(self.menu_type+'_entry', *m.groups())
           elif self.menu_type in ['identify', 'put_in']: #only send one since we only care about all for identify and a for put_in... this is hackish but whatever
              event.dispatch(self.menu_type+'_item','a','a')
           if match.group(1) is None or match.group(1) == match.group(2):
              if self.menu_type in ['put_in','identify','drop', 'loot', 'inventory', 'lootlist']: #these menus do not automatically cancel
                 event.dispatch('menu_done')
              if self.menu_type =='put_in':
                 self.menu_type = 'lootlist'
              else:
                 self.menu_type_clear = True
              
#              event.dispatch('menu_done') #this gets in the way of other menus.. some automatically cancel and some do not
					  #spells, loot_do_what, put_in_type
           else:
              event.dispatch('menu_more')
       
    def cursor_is_on_player(self):
        """ Return whether or not the cursor is currently on the player. """

        first = self.term.display[0].translate(ibm)
        return \
            "To what position do you want to be teleported?" not in first and \
            "Please move the cursor to an unknown object." not in first and \
            "For instructions type a ?" not in first and \
            self.char_at(*self.term.cursor()) != " " and \
            self.term.cursor()[1] > 0

    def char_at(self, x, y):
        """ Return the glyph at the specified coordinates """
        row = self.term.display[y].translate(ibm)
        col = row[x]

        return col
    
    def _dispatch_window_switch_events(self, data):
        match = re.search(r"\1b\[2;(\d+)z", data)
        if match:
           event.dispatch("window_switch", int(match.group(1)))

    def _dispatch_waiting_input_event(self, data):
        match = re.search(r"\x1b\[3z", data)
        if match:
           event.dispatch("waiting_input")

    def process(self, data):
        """
        Callback attached to the output proxy.
        """
       # logging.debug("brain process " + data)

        if "--More--" in self.term.display[self.term.cursor()[1]]:
           event.dispatch('more')
        
	#this is kind of terrible and i'm not even sure i like the event idea in the first place
        #a lot of these each run a regexp on the same thing and hopefully they get cached instead of
        #compiled every time
  
        #note some of the orders of these are important
        self._dispatch_teleport_prompt_event(data) #should be first
        #self._dispatch_status_events(data)
        #self._dispatch_intrinsic_events(data)
        self._dispatch_turn_change_event()
        #self._dispatch_trap_door_event(data)
        #self._dispatch_level_change_event()
        #self._dispatch_level_feature_events(data)
        #self._dispatch_branch_change_event()
        #self._dispatch_shop_entered_event(data)
        self._dispatch_hp_change_event()
        self._dispatch_burden_event()
        self._dispatch_hunger_event()
        self._dispatch_move_event()
        self._dispatch_kill_events(data)
        self._dispatch_altar_events(data)
        self._dispatch_sacrifice_prompt_event(data)
        self._dispatch_sacrifice_response_event(data)
        self._dispatch_eat_prompt_event(data)
        self._dispatch_name_prompt_event(data)
        self._dispatch_wield_prompt_event(data)
        self._dispatch_item_pickup_events(data)
        self._dispatch_name_what_prompt_event(data)
        #self._dispatch_select_prompt_event(data) #disabled because I don't use C currently and it still(?) gets confused with teleport in rare cases
        self._dispatch_extended_command_prompt_event()
        self._dispatch_i_see_no_monster_event(data)
        self._dispatch_unknown_direction_event(data)
        self._dispatch_loot_do_what(data)
        #self._dispatch_put_in_event(data) #done by menu_events
        self._dispatch_stoning_event(data)
        self._dispatch_life_saved_event(data)
        #self._dispatch_identify_list_event(data) #covered by menu
        self._dispatch_identify_done_event(data)
        #self._dispatch_put_in_what_type_event(data) #covered by menu
        self._dispatch_menu_events(data)
#        self._dispatch_inventory_list_event(data) #covered by menu

        self._dispatch_waiting_input_event(data)
        event.dispatch('check_spot', self.char_at(69,18)) 
        #fort broken event
        if "--More--" not in self.term.display[self.term.cursor()[1]]:
            self.prev_cursor = self.term.cursor()
            
        if self.menu_type_clear:
           self.menu_type_clear = False
           self.menu_type = None
