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
        return Interface(mac_address, mtu)
    def add_route(self, prefix, prefix_len, nexthop = None, interface = None):
        assert nexthop or interface
    def add_default_route(self, nexthop, interface = None):
        return self.add_route('0.0.0.0', 0, nexthop, interface)
    def start_process(self, args):
        return Process()
    def run_process(self, args):
        return ("", "")
    def get_routes(self):
        return set()

class Link(object):
    def connect(self, iface):
        pass

class Interface(object):
    def __init__(self, mac_address = None, mtu = None):
        self.name = None
        self.mac_address = mac_address
        self.mtu = mtu
    def add_v4_address(self, address, prefix_len, broadcast = None):
        pass
    def add_v6_address(self, address, prefix_len):
        pass

class Process(object):
    def __init__(self):
        self.pid = os.getpid()
