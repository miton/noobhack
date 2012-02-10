from noobhack.game import events
import logging
import base64
import re
from struct import pack
from random import random
from collections import namedtuple

#altar_pos = (9,13)
#stash_pos = (8,14)
#altar_to_stash = 'n'
#stash_to_altar = 'y'

#altar_pos = (69,18)
#stash_pos = (70,19)

left = (74,11)
right = (75,11)

left_to_right = 'l'
right_to_left = 'h'

Spell = namedtuple('Spell', ['key', 'name', 'remembered', 'fail'])

class Farmer:

    def __init__(self,pending):
        self.hp = None
        self.failed_sacs = {}
        self.last_sac = None
        self.kill_count = 0
        self.kill_total = 0
        self.mode = 'kill'
        self.name_number = 40
        self.hungry = False
        self.abort = False
        self.inventory = {}
        self.spells = {}
        self.spells_names = {}
        self.pending_input = []
        self.pending_input_real = pending
        self.cur_pos = (0,0)
        self.altar_free = None
        self.named = True
        self.sac = False
        self.safe_pray = False
        self.keep_inv = 'DJcyCiPuINQWGRBtFwxSzgOHjghZaAlmoeXs'
        self.unidentified_count = 0 #not likely to be accurate
        self.spell_menu = False
        self.found_spell = False
        self.heal = False
        self.divide_count = 0

        self.death_alive = True
        self.death_spot = None
        self.start_score = None
 
    def listen(self):
        events.dispatcher.add_event_listener('unhungry', self._unhungry_handler)
        events.dispatcher.add_event_listener('loot_do_what', self._loot_do_what_handler)
        events.dispatcher.add_event_listener('stoning', self._stoning_handler)
        events.dispatcher.add_event_listener('died', self._died_handler)
        #events.dispatcher.add_event_listener('inventory_item', self._inventory_item_handler)
        events.dispatcher.add_event_listener('identify_item', self._identify_item_handler)
        events.dispatcher.add_event_listener('identify_done', self._identify_done_handler)
        events.dispatcher.add_event_listener('put_in_type', self._put_in_type_handler)
        events.dispatcher.add_event_listener('lootlist_item', self._lootlist_item_handler)
        events.dispatcher.add_event_listener('loot_item', self._loot_item_handler)
        events.dispatcher.add_event_listener('put_in_item', self._put_in_item_handler)
        events.dispatcher.add_event_listener('drop_item', self._drop_item_handler)
        events.dispatcher.add_event_listener('spell_entry', self._spell_entry_handler)
        events.dispatcher.add_event_listener('menu_done', self._menu_done_handler)
        events.dispatcher.add_event_listener('menu_more', self._menu_more_handler)
#        events.dispatcher.add_event_listener('', self.__handler)

        events.dispatcher.add_event_listener('waiting_input', self._waiting_input_handler)
        events.dispatcher.add_event_listener("more", self._more_handler)
        events.dispatcher.add_event_listener("move", self._move_handler)
        events.dispatcher.add_event_listener("kill", self._kill_handler)
        events.dispatcher.add_event_listener("on_altar", self._on_altar_handler)
        events.dispatcher.add_event_listener("sacrifice_prompt", self._sacrifice_prompt_handler)
        events.dispatcher.add_event_listener("sacrifice_prompt_inv", self._sacrifice_prompt_inv_handler)
        events.dispatcher.add_event_listener("sacrifice_response", self._sacrifice_response_handler)
        events.dispatcher.add_event_listener("eat_prompt", self._eat_prompt_handler)
        events.dispatcher.add_event_listener("eat_prompt_inv", self._eat_prompt_inv_handler)
        events.dispatcher.add_event_listener("name_prompt", self._name_prompt_handler)
        events.dispatcher.add_event_listener("wield_prompt", self._wield_prompt_handler)
        events.dispatcher.add_event_listener("item_pickup", self._item_pickup_handler)
        events.dispatcher.add_event_listener("hp_change", self._hp_change_handler)
        events.dispatcher.add_event_listener("hunger", self._hunger_handler)
        events.dispatcher.add_event_listener("burden", self._burden_handler)
        events.dispatcher.add_event_listener("teleport_prompt", self._teleport_prompt_handler)
        events.dispatcher.add_event_listener("select_name_prompt", self._select_name_prompt_handler)
        events.dispatcher.add_event_listener("name_what", self._name_what_handler)
        events.dispatcher.add_event_listener("check_spot", self._check_spot_handler)
        events.dispatcher.add_event_listener("extended_command_prompt", self._extended_command_prompt_handler)
        events.dispatcher.add_event_listener("fort_broken", self._fort_broken_handler)
        events.dispatcher.add_event_listener("see_no_monster", self._see_no_monster_handler)
        events.dispatcher.add_event_listener("unknown_direction", self._unknown_direction_handler)
        events.dispatcher.add_event_listener("you_hit_it", self._you_hit_it_handler)
        events.dispatcher.add_event_listener("divides", self._divides_handler)
        events.dispatcher.add_event_listener("direction_prompt", self._direction_prompt_handler)
        events.dispatcher.add_event_listener("revive", self._revive_handler)
        events.dispatcher.add_event_listener("score", self._score_handler)

        #events.dispatcher.add_event_listener("", self.__handler)
 
    def _waiting_input_handler(self,event):
        logging.debug("state: %s kill_count: %d kill_total:%d", self.mode, self.kill_count, self.kill_total)
        if self.abort:
           del self.pending_input[:]
           return

        if len(self.pending_input) == 0:
           if self.mode == 'kill':
              if self.cur_pos in [left, right] and self.death_spot:
                 self.pending_input.append('f')
              elif not self.death_spot:
                 self.abort = True
                 del self.pending_input[:]
                 logging.error("aborting because death was not found!")
              else:
                 self.abort = True
                 del self.pending_input[:]
                 logging.error("not on left or right in kill, aborting! %s", self.cur_pos)
           elif self.mode == 'dead':
              if self.hungry:
                 self.pending_input.append('e')
              elif self.cur_pos == left:
                 self.pending_input.append(left_to_right)
              elif self.cur_pos == right:
                 self.pending_input.append(right_to_left)
              else:
                 self.abort = True
                 del self.pending_input[:]
                 logging.error("not on left or right in dead, aborting! %s", self.cur_pos)
           elif self.mode == 'stash':
              if self.cur_pos in [left, right]:
                 self.pending_input.append('#')
              else:
                 self.abort = True
                 del self.pending_input[:]
                 logging.error("not on left or right in stash, aborting! %s", self.cur_pos)
               
        if len(self.pending_input) > 0:#else:# not an else because we need to process the input we just generated
           if len(self.pending_input) > 1 and self.pending_input[1] != '\r' and len(self.pending_input) != 2:
              #the special cases: name input, pray/loot/offer
              logging.debug("waiting_input found more than 1 and not special case: %s", self.pending_input)
           key = self.pending_input.pop(0)
           self.pending_input_real.append(key)
        else:
           logging.debug("end of waiting_input, nothing to do")

    def _revive_handler(self, event):
        self.mode = 'kill'

    def _score_handler(self, event, score):
        if not self.start_score:
           self.start_score = score
        elif score >= start_score + 2500000:
           self.abort = True
           del self.pending_input[:]
           logging.error("aborting due to +2500000 score, start: %d end: %d", self.start_score, score)
        if score >= 1072000000:
           self.abort = True
           del self.pending_input[:]
           logging.error("aborting due to score: %d", score)
           
    def _divides_handler(self, event):
        self.divide_count += 1
        if self.divide_count >= 3 and self.heal:
           self.mode = 'heal'
           self.divide_count = 0

    def _direction_prompt_handler(self, event):
        direction = {left: 'l', right: 'h'}
        self.pending_input.append(direction[self.cur_pos])
 
    def _on_altar_handler(self, event):
        pass
    
    def _unhungry_handler(self, event):
        self.hungry = False
    
    def _menu_done_handler(self, event):
        if self.spell_menu and self.found_spell:
           self.spell_menu = self.found_spell = False
           return
        self.pending_input.append(' ')
    
    def _menu_more_handler(self, event):
        if self.spell_menu and self.found_spell:
           self.spell_menu = self.found_spell = False
           return
        self.pending_input.append(' ')

    def _spell_entry_handler(self, event, key, name, level, school, fail):
        self.spell_menu = True

        self.spells[key] = Spell(key, name, level, fail)
        self.spells_names[name] = key
        if self.mode == 'identify' and name == 'identify':
           if level[-1] != '*':
              self.pending_input.append(key)
              self.found_spell = True
           else:
              #self.mode = 'read'
              self.mode = 'stash'
        elif self.mode == 'heal' and name == 'extra healing':
           if level[-1] != '*':
              self.pending_input.append(key)
              self.found_spell = True
              self.mode = 'split'
           else:
              logging.debug("couldnt heal because forgot it")
       
    def _drop_item_handler(self, event, key, name):
        pass

    def _lootlist_item_handler(self, event, key, name):
        if key not in self.keep_inv:
           self.pending_input.append(key)

    def _put_in_item_handler(self, event, key, name):
        self.pending_input.append('a')
        #if key not in self.keep_inv:
        #   self.pending_input.append(key)

    def _put_in_type_handler(self, event):
        self.pending_input.append('a') #put in what type of object, does this even exist?

    def _loot_do_what_handler(self, event):
        self.pending_input.append('i') #do what with the container

    def _loot_item_handler(self, event, key, name): #this is 'loot which chest'
        match = re.search(r'unsorted', name)
        if match:
           self.pending_input.append(key)
        self.mode = 'kill' 

    def _died_handler(self, event):
        logging.error("aborting because we died (and were hopefully saved)")
        self.abort = True
        del self.pending_input[:]

    def _stoning_handler(self, event):
        logging.error("aborting due to stoning")
        self.abort = True
        del self.pending_input[:]

    def _identify_done_handler(self, event):
        self.unidentified_count = 0
        self.mode = 'stash'

    #def _identify_list_handler(self, event): #unused
    #    self.pending_input.append(',')
   
    def _identify_item_handler(self, event, key, name):
        self.pending_input.append(',') #menu event now only sends us one
        #self.pending_input.append(key) #can't just send , because it would only work with odd number of items

    def _more_handler(self, event):
        self.pending_input.append(' ')

    def _move_handler(self, event, value):
        self.cur_pos = value

    def _check_spot_handler(self, event, pos, value):
        
        if value == '&':
           self.death_spot = pos
        elif self.death_spot == pos:
           self.death_spot = None

    def _kill_handler(self, event, value):
        self.kill_total += 1
        self.mode = 'dead'
 
    def _sacrifice_prompt_handler(self, event, value):
        if value in self.failed_sacs:
           self.pending_input.append('n')
        else:
           self.last_sac = value
           self.pending_input.append('y')
   
    def _sacrifice_prompt_inv_handler(self, event, value):
        self.pending_input.append('\r')
        #self.pending_input.append('w')
	self.mode = 'split'
   
    def _sacrifice_response_handler(self, event, value):
        if value == 'Nothing happens':
           self.failed_sacs[self.last_sac] = True
        elif value == 'You have a feeling of reconciliation':
           self.safe_pray = True

    def _eat_prompt_handler(self, event, value):
        match = re.search(r"(?:food ration)|(?:pancake)|(?:cram ration)|(?:C-ration)|(?:K-ration)|(?:candy bar)|(?:lembas wafers)", value)
        if match:
           self.pending_input.append('y')
           self.hungry = False # does unhungry_handler work?
        else:
           self.pending_input.append('n')

    def _eat_prompt_inv_handler(self, event, value):
        for c in value:
            if c in self.inventory:
               match = re.search("food ration", self.inventory[c])
               if match:
                  self.pending_input.append(c)
                  self.hungry = False
                  return
        logging.error("did not find something to eat!")
        self.abort = True
        del self.pending_input[:]
#        self.pending_input.append('\r') #just loops now

    def _name_prompt_handler(self, event,value):
        self.pending_input.append(base64.encodestring(pack('<Q',self.name_number).rstrip('\x00')).rstrip('='))
        self.pending_input.append('\r')
        self.name_number += 1
        self.named = True

    def _name_what_handler(self, event):
        self.pending_input.append('a')

    def _select_name_prompt_handler(self, event):
        self.pending_input.append(stash_to_altar)
        self.pending_input.append(';')

    def _wield_prompt_handler(self, event, value):
        if self.mode == 'kill' or self.mode == 'sac':
           self.pending_input.append('i')
        elif self.mode == 'split':
           self.pending_input.append('P')
           
    def _item_pickup_handler(self, event, shortcut, name):
        self.inventory[shortcut] = name
        if shortcut not in self.keep_inv:
           self.unidentified_count += 1
        if self.unidentified_count > 10:
           self.mode = 'identify'

    def _hp_change_handler(self, event, value):
        if value <= 100 and not self.abort:
           logging.error("aborting due to low hp")
           #XXX: turn this back on before using! 
           self.abort = True
    
    def _hunger_handler(self, event, value):
        self.hungry = True
        if value != 'Hungry' and not self.abort:
           logging.error("aborting due to more than hungry")
           self.abort = True
    
    def _burden_handler(self, event, value):
        
        if not self.abort:
           logging.error("aborting due to burden")
           self.abort = True
           del self.pending_input[:]
 
    def _teleport_prompt_handler(self, event):
        self.pending_input.append('.')
    
    def _extended_command_prompt_handler(self, event):
        if self.mode == 'sac':
           if self.safe_pray:
	      self.pending_input.append('p')
              self.pending_input.append('\r')
              self.safe_pray = False
           else:
              self.pending_input.append('o')
              self.pending_input.append('\r')
        elif self.mode == 'stash':
              self.pending_input.append('l')
              self.pending_input.append('\r')
 
    def _fort_broken_handler(self, event, value):
        self.abort = True
        logging.error("aborting due to a broken fort")
    
    def _see_no_monster_handler(self, event):
        self.pending_input.append('.')

    def _unknown_direction_handler(self, event):
        self.pending_input.append('.')

    def _you_hit_it_handler(self, event):
        if self.mode == 'split':
           self.mode = 'kill'
           self.pending_input.append('w') 
