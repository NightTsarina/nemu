#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import os, pwd
from netns.node import Node

class __Config(object):
    def __init__(self):
        self._run_as = 65534
        try:
            pwd.getpwnam('nobody')
            self._run_as = 'nobody'
        except:
            pass

    def _set_run_as(self, user):
        if str(user).isdigit():
            uid = int(user)
            try:
                _user = pwd.getpwuid(uid)[0]
            except:
                raise AttributeError("UID %d does not exist" % int(user))
            run_as = int(user)
        else:
            try:
                uid = pwd.getpwnam(str(user))[2]
            except:
                raise AttributeError("User %s does not exist" % str(user))
            run_as = str(user)
        if uid == 0:
            raise AttributeError("Cannot run as root by default")
        self._run_as = run_as
        return run_as
    def _get_run_as(self):
        return self._run_as
    run_as = property(_get_run_as, _set_run_as, None,
            "Default user to run applications as")

config = __Config()
get_nodes = Node.get_nodes

# FIXME: set atfork hooks
# http://code.google.com/p/python-atfork/source/browse/atfork/__init__.py

def set_cleanup_hooks(on_exit = False, on_signals = []):
    pass

class Link(object):
    def connect(self, iface):
        pass


