# vim:ts=4:sw=4:et:ai:sts=4

import os, re, socket, weakref
import netns.iproute

__all__ = ['NodeInterface', 'P2PInterface', 'ExternalInterface']

class _Interface(object):
    """Just a base class for the *Interface classes: assign names and handle
    destruction."""
    _nextid = 0
    @staticmethod
    def _gen_next_id():
        n = _Interface._nextid
        _Interface._nextid += 1
        return n

    @staticmethod
    def _gen_if_name():
        n = _Interface._gen_next_id()
        # Max 15 chars
        return "NETNSif-%.4x%.3x" % (os.getpid(), n)

class _NSInterface(_Interface):
    """Add user-facing methods for interfaces that go into a netns."""
    def destroy(self):
        try:
            # no need to check _ns_if, exceptions are ignored anyways
            self._slave.del_if(self._ns_if)
        except:
            # Maybe it already went away, or the slave died. Anyway, better
            # ignore the error
            pass

    def __del__(self):
        self.destroy()

    @property
    def index(self):
        return self._ns_if

    # some black magic to automatically get/set interface attributes
    def __getattr__(self, name):
        if (name not in interface.changeable_attributes):
            raise AttributeError("'%s' object has no attribute '%s'" %
                    (self.__class__.__name__, name))
        # I can use attributes now, as long as they are not in
        # changeable_attributes
        iface = self._slave.get_if_data(self._ns_if)
        return getattr(iface, name)

    def __setattr__(self, name, value):
        if (name not in interface.changeable_attributes):
            if name[0] != '_': # forbid anything that doesn't start with a _
                raise AttributeError("'%s' object has no attribute '%s'" %
                        (self.__class__.__name__, name))
            super(_Interface, self).__setattr__(name, value)
            return
        iface = interface(index = self._ns_if)
        setattr(iface, name, value)
        return self._slave.set_if(iface)

    def add_v4_address(self, address, prefix_len, broadcast = None):
        addr = ipv4address(address, prefix_len, broadcast)
        self._slave.add_addr(self._ns_if, addr)

    def add_v6_address(self, address, prefix_len):
        addr = ipv6address(address, prefix_len)
        self._slave.add_addr(self._ns_if, addr)

    def del_v4_address(self, address, prefix_len, broadcast = None):
        addr = ipv4address(address, prefix_len, broadcast)
        self._slave.del_addr(self._ns_if, addr)

    def del_v6_address(self, address, prefix_len):
        addr = ipv6address(address, prefix_len)
        self._slave.del_addr(self._ns_if, addr)

    def get_addresses(self):
        addresses = self._slave.get_addr_data(self._ns_if)
        ret = []
        for a in addresses:
            if hasattr(a, 'broadcast'):
                ret.append(dict(
                    address = a.address,
                    prefix_len = a.prefix_len,
                    broadcast = a.broadcast,
                    family = 'inet'))
            else:
                ret.append(dict(
                    address = a.address,
                    prefix_len = a.prefix_len,
                    family = 'inet6'))
        return ret

class NodeInterface(_NSInterface):
    """Class to create and handle a virtual interface inside a name space, it
    can be connected to a Link object with emulation of link
    characteristics."""
    def __init__(self, node):
        """Create a new interface. `node' is the name space in which this
        interface should be put."""
        if1 = interface(name = self._gen_if_name())
        if2 = interface(name = self._gen_if_name())
        ctl, ns = netns.iproute.create_if_pair(if1, if2)
        try:
            netns.iproute.change_netns(ns, node.pid)
        except:
            netns.iproute.del_if(ctl)
            # the other interface should go away automatically
            raise
        self._ctl_if = ctl.index
        self._ns_if = ns.index
        self._slave = node._slave
        node._add_interface(self)

    @property
    def control_index(self):
        return self._ctl_if

class P2PInterface(_NSInterface):
    """Class to create and handle point-to-point interfaces between name
    spaces, without using Link objects. Those do not allow any kind of traffic
    shaping.
    As two interfaces need to be created, instead of using the class
    constructor, use the P2PInterface.create_pair() static method."""
    @staticmethod
    def create_pair(node1, node2):
        """Create and return a pair of connected P2PInterface objects, assigned
        to name spaces represented by `node1' and `node2'."""
        if1 = interface(name = P2PInterface._gen_if_name())
        if2 = interface(name = P2PInterface._gen_if_name())
        pair = netns.iproute.create_if_pair(if1, if2)
        try:
            netns.iproute.change_netns(pair[0], node1.pid)
            netns.iproute.change_netns(pair[1], node2.pid)
        except:
            netns.iproute.del_if(pair[0])
            # the other interface should go away automatically
            raise

        o1 = P2PInterface.__new__(P2PInterface)
        o1._slave = node1._slave
        o1._ns_if = pair[0].index
        node1._add_interface(o1)

        o2 = P2PInterface.__new__(P2PInterface)
        o2._slave = node2._slave
        o2._ns_if = pair[1].index
        node2._add_interface(o2)

        return o1, o2

    def __init__(self):
        "Not to be called directly. Use P2PInterface.create_pair()"
        raise RuntimeError(P2PInterface.__init__.__doc__)

class ExternalInterface(_Interface):
    """Class to handle already existing interfaces. This kind of interfaces can
    only be connected to Link objects and not assigned to a name space.
    On destruction, the code will try to restore the interface to the state it
    was in before being imported into netns."""
    def __init__(self, iface):
        iface = netns.iproute.get_if(iface)
        self._ctl_if = iface.index
        self._original_state = iface

    # FIXME: register somewhere for destruction!
    def destroy(self): # override: restore as much as possible
        try:
            netns.iproute.set_if(self._original_state)
        except:
            pass

    @property
    def control_index(self):
        return self._ctl_if

class ExternalNodeInterface(_NSInterface):
    """Class to handle already existing interfaces inside a name space, usually
    just the loopback device, but it can be other user-created interfaces. On
    destruction, the code will try to restore the interface to the state it was
    in before being imported into netns."""
    def __init__(self, node, iface):
        iface = node._slave.get_if_data(iface)
        self._original_state = iface

        self._ns_if = iface.index
        self._slave = node._slave
        node._add_interface(self)

    # FIXME: register somewhere for destruction!
    def destroy(self): # override: restore as much as possible
        try:
            self._slave.set_if(self._original_state)
        except:
            pass

# don't look after this :-)

# helpers
def _any_to_bool(any):
    if isinstance(any, bool):
        return any
    if isinstance(any, int):
        return any != 0
    if isinstance(any, str):
        if any.isdigit():
            return int(any) != 0
        if any.lower() == "true":
            return True
        if any.lower() == "false":
            return False
        return any != ""
    return bool(any)

def _positive(val):
    v = int(val)
    if v <= 0:
        raise ValueError("Invalid value: %d" % v)
    return v

def _fix_lladdr(addr):
    foo = addr.lower()
    if ':' in addr:
        # Verify sanity and split
        m = re.search('^' + ':'.join(['([0-9a-f]{1,2})'] * 6) + '$', foo)
        if m is None:
            raise ValueError("Invalid address: `%s'." % addr)
        # Fill missing zeros and glue again
        return ':'.join(('0' * (2 - len(x)) + x for x in m.groups()))

    # Fill missing zeros
    foo = '0' * (12 - len(foo)) + foo
    # Verify sanity and split
    m = re.search('^' + '([0-9a-f]{2})' * 6 + '$', foo)
    if m is None:
        raise ValueError("Invalid address: `%s'." % addr)
    # Glue
    return ":".join(m.groups())

def _make_getter(attr, conv = lambda x: x):
    def getter(self):
        return conv(getattr(self, attr))
    return getter

def _make_setter(attr, conv = lambda x: x):
    def setter(self, value):
        if value == None:
            setattr(self, attr, None)
        else:
            setattr(self, attr, conv(value))
    return setter

# classes for internal use
class interface(object):
    """Class for internal use. It is mostly a data container used to easily
    pass information around; with some convenience methods."""
    @classmethod
    def parse_ip(cls, line):
        """Parse a line of ouput from `ip -o link list' and construct and
        return a new object with the data."""
        match = re.search(r'^(\d+): (\S+): <(\S+)> mtu (\d+) qdisc \S+' +
                r'.*link/\S+ ([0-9a-f:]+) brd ([0-9a-f:]+)', line)
        flags = match.group(3).split(",")
        return cls(
                index   = match.group(1),
                name    = match.group(2),
                up      = "UP" in flags,
                mtu     = match.group(4),
                lladdr  = match.group(5),
                arp     = not ("NOARP" in flags),
                broadcast = match.group(6),
                multicast = "MULTICAST" in flags)

    # information for other parts of the code
    changeable_attributes = ["name", "mtu", "lladdr", "broadcast", "up",
            "multicast", "arp"]

    # Index should be read-only
    index = property(_make_getter("_index"))
    up = property(_make_getter("_up"), _make_setter("_up", _any_to_bool))
    mtu = property(_make_getter("_mtu"), _make_setter("_mtu", _positive))
    lladdr = property(_make_getter("_lladdr"),
            _make_setter("_lladdr", _fix_lladdr))
    arp = property(_make_getter("_arp"), _make_setter("_arp", _any_to_bool))
    multicast = property(_make_getter("_mc"), _make_setter("_mc", _any_to_bool))

    def __init__(self, index = None, name = None, up = None, mtu = None,
            lladdr = None, broadcast = None, multicast = None, arp = None):
        self._index = _positive(index) if index is not None else None
        self.name = name
        self.up = up
        self.mtu = mtu
        self.lladdr = lladdr
        self.broadcast = broadcast
        self.multicast = multicast
        self.arp = arp

    def __repr__(self):
        s = "%s.%s(index = %s, name = %s, up = %s, mtu = %s, lladdr = %s, "
        s += "broadcast = %s, multicast = %s, arp = %s)"
        return s % (self.__module__, self.__class__.__name__,
                self.index.__repr__(), self.name.__repr__(),
                self.up.__repr__(), self.mtu.__repr__(),
                self.lladdr.__repr__(), self.broadcast.__repr__(),
                self.multicast.__repr__(), self.arp.__repr__())

    def __sub__(self, o):
        """Compare attributes and return a new object with just the attributes
        that differ set (with the value they have in the first operand). The
        index remains equal to the first operand."""
        name = None if self.name == o.name else self.name
        up = None if self.up == o.up else self.up
        mtu = None if self.mtu == o.mtu else self.mtu
        lladdr = None if self.lladdr == o.lladdr else self.lladdr
        broadcast = None if self.broadcast == o.broadcast else self.broadcast
        multicast = None if self.multicast == o.multicast else self.multicast
        arp = None if self.arp == o.arp else self.arp
        return self.__class__(self.index, name, up, mtu, lladdr, broadcast,
                multicast, arp)

class address(object):
    """Class for internal use. It is mostly a data container used to easily
    pass information around; with some convenience methods. __eq__ and __hash__
    are defined just to be able to easily find duplicated addresses."""
    @classmethod
    def parse_ip(cls, line):
        """Parse a line of ouput from `ip -o addr list' (after trimming the
        index and interface name) and construct and return a new object with
        the data."""
        match = re.search(r'^inet ([0-9.]+)/(\d+)(?: brd ([0-9.]+))?', line)
        if match != None:
            return ipv4address(
                address     = match.group(1),
                prefix_len  = match.group(2),
                broadcast   = match.group(3))

        match = re.search(r'^inet6 ([0-9a-f:]+)/(\d+)', line)
        if match != None:
            return ipv6address(
                address     = match.group(1),
                prefix_len  = match.group(2))

        raise RuntimeError("Problems parsing ip command output")

    # broadcast is not taken into account for differentiating addresses
    def __eq__(self, o):
        if not isinstance(o, address):
            return False
        return (self.family == o.family and self.address == o.address and
                self.prefix_len == o.prefix_len)

    def __hash__(self):
        h = (self.address.__hash__() ^ self.prefix_len.__hash__() ^
                self.family.__hash__())
        return h
 
class ipv4address(address):
    def __init__(self, address, prefix_len, broadcast):
        self.address = address
        self.prefix_len = int(prefix_len)
        self.broadcast = broadcast
        self.family = socket.AF_INET

    def __repr__(self):
        s = "%s.%s(address = %s, prefix_len = %d, broadcast = %s)"
        return s % (self.__module__, self.__class__.__name__,
                self.address.__repr__(), self.prefix_len,
                self.broadcast.__repr__())

class ipv6address(address):
    def __init__(self, address, prefix_len):
        self.address = address
        self.prefix_len = int(prefix_len)
        self.family = socket.AF_INET6

    def __repr__(self):
        s = "%s.%s(address = %s, prefix_len = %d)"
        return s % (self.__module__, self.__class__.__name__,
                self.address.__repr__(), self.prefix_len)

