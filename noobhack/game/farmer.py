from noobhack.game import events

class Farmer:

    def __init__(self):

    def listen(self):
        #events.dispatcher.add_event_listener("status", self._status_handler)
        #events.dispatcher.add_event_listener("intrinsic", self._intrinsic_handler)
"""
    def _intrinsic_handler(self, event, name, value):
        if name in self.intrinsics and value == False:
            self.intrinsics.remove(name)
        elif name not in self.intrinsics and value == True:
            self.intrinsics.add(name)

    def _status_handler(self, event, name, value):
        if name in self.status and value == False:
            self.status.remove(name)
        elif name not in self.status and value == True:
            self.status.add(name)
"""
    def _kill_handler(self, event, name, value):
        pass
