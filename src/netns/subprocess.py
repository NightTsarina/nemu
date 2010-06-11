#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import os, signal

class Subprocess(object):
    def __init__(self, uid, gid, file, argv, cwd = None, env = None,
            stdin = None, stdout = None, stderr = None):
        self._pid = -1

    @property
    def pid(self):
        return self._pid

    def poll(self):
        return None

    def wait(self):
        return 0

    def kill(self, sig = signal.SIGTERM):
        return self._pid
