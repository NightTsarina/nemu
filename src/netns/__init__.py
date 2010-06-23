#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import os, pwd
from netns.node import Node

class __Config(object):
    def __init__(self):
        self._run_as = 65535
        try:
            self._run_as = pwd.getpwnam('nobody')[2]
        except:
            pass

    def _set_run_as(self, uid):
        if type(uid) != int:
            uid = pwd.getpwnam(uid)[2]
        if uid == 0:
            raise AttributeError("Cannot run as root by default")
        self._run_as = uid
    def _get_run_as(self):
        return self._run_as
    run_as = property(_get_run_as, _set_run_as, None,
            "Default uid to run applications as")

config = __Config()
get_nodes = Node.get_nodes

def set_cleanup_hooks(on_exit = False, on_signals = []):
    pass

class Link(object):
    def connect(self, iface):
        pass


