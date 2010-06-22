#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import os, socket, sys, traceback, unshare
import netns.protocol

class Node(object):
    def __init__(self, debug = False):
        """Create a new node in the emulation. Implemented as a separate
        process in a new network name space. Requires root privileges to run.

        If keepns is true, the network name space is not created and can be run
        as a normal user, for testing. If debug is true, details of the
        communication protocol are printed on stderr."""
        fd, pid = _start_child(debug)
        self._pid = pid
        self._slave = netns.protocol.Client(fd, debug)
        self._valid = True
    @property
    def pid(self):
        return self._pid
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

# Handle the creation of the child; parent gets (fd, pid), child creates and
# runs a Server(); never returns.
# Requires CAP_SYS_ADMIN privileges to run.
def _start_child(debug = False):
    # Create socket pair to communicate
    (s0, s1) = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM, 0)
    # Spawn a child that will run in a loop
    pid = os.fork()
    if pid:
        s1.close()
        return (s0, pid)

    try:
        s0.close()
        srv = netns.protocol.Server(s1, debug)
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

