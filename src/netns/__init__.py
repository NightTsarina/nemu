#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import os
import netns.protocol

class __Config(object):
    def __init__(self):
        self.run_as = None

config = __Config()
__nodes = set()

def get_nodes():
    return set(__nodes)

def set_cleanup_hooks(on_exit = False, on_signals = []):
    pass

class Node(object):
    def __init__(self):
        self.slave_pid, self.slave_fd = spawn_slave()
        self.valid = True
    @property
    def pid(self):
        return self.slave_pid
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
        self.valid = True
    def add_v4_address(self, address, prefix_len, broadcast = None):
        pass
    def add_v6_address(self, address, prefix_len):
        pass

class Process(object):
    def __init__(self):
        self.pid = os.getpid()
        self.valid = True

import os, socket, sys, traceback, unshare
def spawn_slave():
    (s0, s1) = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM, 0)
    #ppid = os.getpid()
    pid = os.fork()
    if pid:
        helo = s0.recv(4096).rstrip().split(None, 1)
        if int(helo[0]) / 100 != 2:
            raise RuntimeError("Failed to start slave node: %s" % helo[1])
        s1.close()
        return (pid, s0)

    srv = netns.protocol.Server(s1.fileno())
    try:
        s0.close()
        #unshare.unshare(unshare.CLONE_NEWNET)
    except BaseException, e:
        srv.abort(str(e))

    # Try block just in case...
    try:
        srv.run()
    except:
        traceback.print_exc(file = sys.stderr)
        os._exit(1)
    else:
        os._exit(0)
    # NOTREACHED


