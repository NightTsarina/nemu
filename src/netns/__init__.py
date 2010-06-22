#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import os
from netns.node import Node

class __Config(object):
    def __init__(self):
        self.run_as = None

config = __Config()
__nodes = set()

def get_nodes():
    return set(__nodes)

def set_cleanup_hooks(on_exit = False, on_signals = []):
    pass

class Link(object):
    def connect(self, iface):
        pass


