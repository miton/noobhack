from noobhack.game import events
import logging
import base64
import re
from struct import pack

altar_pos = (69,18)
stash_pos = (70,19)

class Farmer:

    def __init__(self,pending):
        self.hp = None
        self.failed_sacs = {}
        self.last_sac = None
        self.kill_count = 0
        self.mode = 'kill'
        self.name_number = 40
        self.hungry = False
        self.abort = False
        self.inventory = {}
        self.pending_input = pending
        self.cur_location = (0,0)
        self.altar_free = None
        self.named = True

    def listen(self):
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
        #events.dispatcher.add_event_listener("", self.__handler)
 
    def _waiting_input_handler(self,event):
        logging.debug("state: %s kill_count: %d", self.mode, self.kill_count)
        if self.abort:
           del self.pending_input[:]
           return

	if len(self.pending_input) == 0:
           if self.mode == 'kill' or self.mode == 'split':
              if self.cur_pos == altar_pos:
                 self.pending_input.append('n')
              elif self.cur_pos == stash_pos: 
	         if self.hungry:
                    self.pending_input.append('e')
                 elif self.altar_free:
                    self.pending_input.append('.')
                 else:
                    if not self.named:
                       self.pending_input.append('C')
                    else:
                       self.pending_input.append('y')
              else:
                    self.abort == True
                    logging.error('not on stash or altar, aborting! %s', self.cur_pos)
           elif self.mode == 'sac':
              if self.cur_pos == stash_pos:
                 if self.altar_free:
                    self.pending_input.append('y')
                 else:
                    self.pending_input.append('.')
              elif self.cur_pos == altar_pos:
                 self.pending_input.append('#')
              else:
                 self.abort = True
                 logging.error('not on stash or altar (in sac), abroting! %s', self.cur_pos)
           
    def _on_altar_handler(self, event):
        pass
    
    def _more_handler(self, event):
        self.pending_input.append(' ')

    def _move_handler(self, event, value):
        self.cur_pos = value

    def _check_spot_handler(self, event, value):
        if value == '%':
           self.altar_free = True
        else:
           self.altar_free = False
    
    def _kill_handler(self, event, value):
        self.kill_count += 1
        if self.kill_count >= 5 and self.mode == 'kill':
           self.mode = 'sac'
           self.pending_input.append('w')
        elif self.mode == 'split':
           self.mode = 'kill'
           self.pending_input.append('w')
        self.named = False
 
    def _sacrifice_prompt_handler(self, event, value):
        if value in self.failed_sacs:
           self.pending_input.append('n')
        else:
           self.last_sac = value
           self.pending_input.append('y')
   
    def _sacrifice_prompt_inv_handler(self, event, value):
        self.mode = 'split'
   
    def _sacrifice_response_handler(self, event, value):
        if value == 'Nothing happens':
           self.failed_sacs[self.last_sac] = True

    def _eat_prompt_handler(self, event, value):
        self.pending_input.append('n')

    def _eat_prompt_inv_handler(self, event, value):
        for c in value:
            if c in self.inventory:
               match = re.search("food ration", self.inventory[c])
               if match:
                  self.pending_input.append(c)
                  return

    def _name_prompt_handler(self, event,value):
        self.pending_input.append(base64.encodestring(pack('<Q',self.name_number).rstrip('\x00')))
        self.pending_input.append('\r')
        self.name_number += 1
        self.named = True

    def _name_what_handler(self, event):
        self.pending_input.append('a')

    def _select_name_prompt_handler(self, event):
        self.pending_input.append('h')
        self.pending_input.append('k')
        self.pending_input.append(';')

    def _wield_prompt_handler(self, event, value):
        if self.mode == 'kill':
           self.pending_input.append('i')
        elif self.mode == 'split' or self.mode == 'sac':
           self.pending_input.append('p')
           
    def _item_pickup_handler(self, event, shortcut, name):
        self.inventory[shortcut] = name

    def _hp_change_handler(self, event, value):
        if value <= 100:
           logging.error("aborting due to low hp")
           #XXX: turn this back on before using! 
           #self.abort = True
    
    def _hunger_handler(self, event, value):
        self.hungry = True
        if value != 'Hungry':
           logging.error("aborting due to more than hungry")
           self.abort = True
    
    def _burden_handler(self, event, value):
        self.abort = True
        logging.error("aborting due to burden")
 
    def _teleport_prompt_handler(self, event):
        self.pending_input.append('.')
    
    def _extended_command_prompt_handler(self, event):
        self.pending_input.append('o')
        self.pending_input.append('\r')
 
    def _fort_broken_handler(self, event, value):
        self.abort = True
        logging.error("aborting due to a broken fort")

 
