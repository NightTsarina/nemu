#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import os, socket, sys, traceback, unshare, weakref
import netns.protocol, netns.subprocess_

class Node(object):
    _nodes = weakref.WeakValueDictionary()
    _nextnode = 0
    @classmethod
    def get_nodes(cls):
        s = sorted(Node._nodes.items(), key = lambda x: x[0])
        return [ x[1] for x in s ]

    def __init__(self, debug = False, nonetns = False):
        """Create a new node in the emulation. Implemented as a separate
        process in a new network name space. Requires root privileges to run.

        If keepns is true, the network name space is not created and can be run
        as a normal user, for testing. If debug is true, details of the
        communication protocol are printed on stderr."""
        fd, pid = _start_child(debug, nonetns)
        self._pid = pid
        self._slave = netns.protocol.Client(fd, fd, debug)
        self._processes = weakref.WeakValueDictionary()
        Node._nodes[Node._nextnode] = self
        Node._nextnode += 1

    def __del__(self):
        self.destroy()

    def destroy(self):
        for p in self._processes.values():
            p.destroy()
        del self._processes
        del self._pid
        self._slave.shutdown()
        del self._slave

    # Subprocesses
    def _add_subprocess(self, subprocess):
        self._processes[subprocess.pid] = subprocess

    def Subprocess(self, *kargs, **kwargs):
        return netns.subprocess_.Subprocess(self, *kargs, **kwargs)
    def Popen(self, *kargs, **kwargs):
        return netns.subprocess_.Popen(self, *kargs, **kwargs)
    def system(self, *kargs, **kwargs):
        return netns.subprocess_.system(self, *kargs, **kwargs)
    def backticks(self, *kargs, **kwargs):
        return netns.subprocess_.backticks(self, *kargs, **kwargs)
    def backticks_raise(self, *kargs, **kwargs):
        return netns.subprocess_.backticks_raise(self, *kargs, **kwargs)

    @property
    def pid(self):
        return self._pid

    def add_if(self, mac_address = None, mtu = None):
        return Interface(mac_address, mtu)
    def add_route(self, prefix, prefix_len, nexthop = None, interface = None):
        assert nexthop or interface
    def add_default_route(self, nexthop, interface = None):
        return self.add_route('0.0.0.0', 0, nexthop, interface)
    def get_routes(self):
        return set()

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

# Handle the creation of the child; parent gets (fd, pid), child creates and
# runs a Server(); never returns.
# Requires CAP_SYS_ADMIN privileges to run.
def _start_child(debug, nonetns):
    # Create socket pair to communicate
    (s0, s1) = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM, 0)
    # Spawn a child that will run in a loop
    pid = os.fork()
    if pid:
        s1.close()
        return (s0, pid)

    # FIXME: clean up signal handers, atexit functions, etc.
    try:
        s0.close()
        srv = netns.protocol.Server(s1, s1, debug)
        if not nonetns:
            unshare.unshare(unshare.CLONE_NEWNET)
        srv.run()
    except BaseException, e:
        s = "Slave node aborting: %s\n" % str(e)
        sep = "=" * 70 + "\n"
        sys.stderr.write(s + sep)
        traceback.print_exc(file=sys.stdout)
        sys.stderr.write(sep)
        try:
            # try to pass the error to parent, if possible
            s1.send("500 " + s)
        except:
            pass
        os._exit(1)

    os._exit(0)
    # NOTREACHED

