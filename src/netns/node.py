# vim:ts=4:sw=4:et:ai:sts=4
import os, socket, sys, traceback, unshare, weakref
from netns.environ import *
import netns.interface, netns.protocol, netns.subprocess_

__all__ = ['Node', 'get_nodes', 'import_if']

class Node(object):
    _nodes = weakref.WeakValueDictionary()
    _nextnode = 0
    @staticmethod
    def get_nodes():
        s = sorted(Node._nodes.items(), key = lambda x: x[0])
        return [x[1] for x in s]

    def __init__(self, nonetns = False, forward_X11 = False):
        """Create a new node in the emulation. Implemented as a separate
        process in a new network name space. Requires root privileges to run.

        If keepns is true, the network name space is not created and can be
        run as a normal user, for testing."""

        # Initialize attributes, in case something fails during __init__
        self._pid = self._slave = None
        self._processes = weakref.WeakValueDictionary()
        self._interfaces = weakref.WeakValueDictionary()
        self._auto_interfaces = [] # just to keep them alive!

        fd, pid = _start_child(nonetns)
        self._pid = pid
        debug("Node(0x%x).__init__(), pid = %s" % (id(self), pid))
        self._slave = netns.protocol.Client(fd, fd)
        if forward_X11:
            self._slave.enable_x11_forwarding()

        Node._nodes[Node._nextnode] = self
        Node._nextnode += 1

        # Bring loopback up
        if not nonetns:
            self.get_interface("lo").up = True

    def __del__(self):
        debug("Node(0x%x).__del__()" % id(self))
        self.destroy()

    def destroy(self):
        if not self._pid:
            return
        debug("Node(0x%x).destroy()" % id(self))
        for p in self._processes.values():
            p.destroy()
        self._processes.clear()

        # Use get_interfaces to force a rescan
        for i in self.get_interfaces():
            i.destroy()
        self._interfaces.clear()

        if self._slave:
            self._slave.shutdown()

        exitcode = eintr_wrapper(os.waitpid, self._pid, 0)[1]
        if exitcode != 0:
            error("Node(0x%x) process %d exited with non-zero status: %d" %
                    (id(self), self._pid, exitcode))
        self._pid = self._slave = None

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

    def add_tap(self, use_pi = False, **kwargs):
        i = netns.interface.TapNodeInterface(self, use_pi)
        for k, v in kwargs.items():
            setattr(i, k, v)
        return i

    def add_tun(self, use_pi = False, **kwargs):
        i = netns.interface.TunNodeInterface(self, use_pi)
        for k, v in kwargs.items():
            setattr(i, k, v)
        return i

    def import_if(self, interface):
        return netns.interface.ImportedNodeInterface(self, interface)

    def del_if(self, iface):
        """Doesn't destroy the interface if it wasn't created by us."""
        del self._interfaces[iface.index]
        iface.destroy()

    def get_interface(self, name):
        return [i for i in self.get_interfaces() if i.name == name][0]

    def get_interfaces(self):
        if not self._slave:
            return []
        ifaces = self._slave.get_if_data()
        for i in ifaces:
            if i not in self._interfaces:
                iface = netns.interface.ImportedNodeInterface(self, i,
                        migrate = False)
                self._auto_interfaces.append(iface) # keep it referenced!
                self._interfaces[i] = iface
        # by the way, clean up _interfaces
        for i in list(self._interfaces): # copy before deleting!
            if i not in ifaces:
                notice("Node(0x%x): interface #%d went away." % (id(self), i))
                self._interfaces[i].destroy()
                del self._interfaces[i]

        return sorted(self._interfaces.values(), key = lambda x: x.index)

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
def _start_child(nonetns):
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
        srv = netns.protocol.Server(s1, s1)
        if not nonetns:
            # create new name space
            unshare.unshare(unshare.CLONE_NEWNET)
            # Enable packet forwarding
            execute([sysctl_path, '-w', 'net.ipv4.ip_forward=1'])
            execute([sysctl_path, '-w', 'net.ipv6.conf.default.forwarding=1'])
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
import_if = netns.interface.ImportedInterface
