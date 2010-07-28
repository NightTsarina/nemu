#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import os, socket, sys, traceback, unshare, weakref
import netns.protocol, netns.subprocess_

__all__ = ['Node', 'get_nodes']

class Node(object):
    _nodes = weakref.WeakValueDictionary()
    _nextnode = 0
    @staticmethod
    def get_nodes():
        s = sorted(Node._nodes.items(), key = lambda x: x[0])
        return [x[1] for x in s]

    def __init__(self, debug = False, nonetns = False):
        """Create a new node in the emulation. Implemented as a separate
        process in a new network name space. Requires root privileges to run.

        If keepns is true, the network name space is not created and can be run
        as a normal user, for testing. If debug is true, details of the
        communication protocol are printed on stderr."""
        fd, pid = _start_child(debug, nonetns)
        self._pid = pid
        self._debug = debug
        self._slave = netns.protocol.Client(fd, fd, debug)
        self._processes = weakref.WeakValueDictionary()
        self._interfaces = weakref.WeakValueDictionary()

        Node._nodes[Node._nextnode] = self
        Node._nextnode += 1

    def __del__(self):
        if self._debug: # pragma: no cover
            sys.stderr.write("*** Node(%s) __del__\n" % self.pid)
        self.destroy()

    def destroy(self):
        if self._debug: # pragma: no cover
            sys.stderr.write("*** Node(%s) destroy\n" % self.pid)
        for p in self._processes.values():
            p.destroy()
        del self._processes
        # Use get_interfaces to force a rescan
        for i in self.get_interfaces():
            i.destroy()
        del self._interfaces
        del self._pid
        self._slave.shutdown()
        del self._slave

    @property
    def pid(self):
        return self._pid

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

    # Interfaces
    def _add_interface(self, interface):
        self._interfaces[interface.index] = interface

    def add_if(self, **kwargs):
        i = netns.interface.NodeInterface(self)
        for k, v in kwargs.items():
            setattr(i, k, v)
        return i

    def del_if(self, iface):
        """Doesn't destroy the interface if it wasn't created by us."""
        del self._interfaces[iface.index]
        iface.destroy()

    def get_interfaces(self):
        ifaces = self._slave.get_if_data()
        ret = []
        for i in ifaces:
            if i not in self._interfaces:
                ret.append(netns.interface.ForeignNodeInterface(self, i))
            else:
                ret.append(self._interfaces[i])
        # by the way, clean up _interfaces
        for i in list(self._interfaces): # copy before deleting!
            if i not in ifaces:
                if self._debug:
                    sys.stderr.write("WARNING: interface #%d went away." % i)
                del self._interfaces[i]

        return sorted(ret, key = lambda x: x.index)

    def route(self, tipe = 'unicast', prefix = None, prefix_len = 0,
            nexthop = None, interface = None, metric = 0):
        return netns.iproute.route(tipe, prefix, prefix_len, nexthop,
                interface.index if interface else None, metric)

    def add_route(self, *args, **kwargs):
        # Accepts either a route object or all its constructor's parameters
        if len(args) == 1 and not kwargs:
            r = args[0]
        else:
            r = self.route(*args, **kwargs)
        return self._slave.add_route(r)

    def del_route(self, *args, **kwargs):
        if len(args) == 1 and not kwargs:
            r = args[0]
        else:
            r = self.route(*args, **kwargs)
        return self._slave.del_route(r)

    def get_routes(self):
        return self._slave.get_route_data()

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

get_nodes = Node.get_nodes

