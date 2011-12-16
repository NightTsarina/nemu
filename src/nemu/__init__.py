# vim:ts=4:sw=4:et:ai:sts=4
# -*- coding: utf-8 -*-

# Copyright 2010, 2011 INRIA
# Copyright 2011 Martín Ferrari <martin.ferrari@gmail.com>
#
# This file is part of Nemu.
#
# Nemu is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2, as published by the Free
# Software Foundation.
#
# Nemu is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# Nemu.  If not, see <http://www.gnu.org/licenses/>.

import os, pwd
from nemu.node import *
from nemu.interface import *

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


# FIXME: set atfork hooks
# http://code.google.com/p/python-atfork/source/browse/atfork/__init__.py

def set_cleanup_hooks(on_exit = False, on_signals = []):
    pass


