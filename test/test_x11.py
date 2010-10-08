#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4
import netns
import os

netns.environ.set_log_level(netns.environ.LOG_DEBUG)

n = netns.Node()
err = file('/tmp/out_y', 'wb')
a = n.Popen(['xterm'], stderr = err)
a.wait()

