#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import os

class __Config(object):
    def __init__(self):
        self.run_as = None

config = __Config()

def get_nodes():
    return set()
def set_cleanup_hooks(on_exit = False, on_signals = []):
    pass

class Node(object):
    def __init__(self):
        self.pid = 0
    def add_if(self, mac_address = None, mtu = None):
        return Interface()
    def start_process(self, args):
        return Process()
    def run_process(self, args):
        return ("", "")

class Link(object):
    def connect(self, iface):
        pass

class Interface(object):
    def __init__(self):
        self.name = None
        self.mac_address = None
    def add_v4_address(self, addr, prefix_len, broadcast = None):
        pass
    def add_v6_address(self, addr, prefix_len):
        pass

class Process(object):
    def __init__(self):
        self.pid = os.getpid()
