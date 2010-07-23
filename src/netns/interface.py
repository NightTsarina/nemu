# vim:ts=4:sw=4:et:ai:sts=4

import os, re, socket, weakref
import netns.iproute

__all__ = ['NodeInterface', 'P2PInterface', 'ForeignInterface',
'ForeignNodeInterface', 'Link']

class Interface(object):
    """Just a base class for the *Interface classes: assign names and handle
    destruction."""
    _nextid = 0
    @staticmethod
    def _gen_next_id():
        n = Interface._nextid
        Interface._nextid += 1
        return n

    @staticmethod
    def _gen_if_name():
        n = Interface._gen_next_id()
        # Max 15 chars
        return "NETNSif-%.4x%.3x" % (os.getpid(), n)

    def __init__(self, index):
        self._idx = index

    def __del__(self):
        self.destroy()

    def destroy(self):
        raise NotImplementedError

    @property
    def index(self):
        """Interface index as seen by the kernel."""
        return self._idx

    @property
    def control(self):
        """Associated interface in the main name space (if it exists). Only
        control interfaces can be put into a Link, for example."""
        return None

class NSInterface(Interface):
    """Add user-facing methods for interfaces that go into a netns."""
    def __init__(self, node, index):
        super(NSInterface, self).__init__(index)
        self._slave = node._slave
        node._add_interface(self)

    # some black magic to automatically get/set interface attributes
    def __getattr__(self, name):
        iface = self._slave.get_if_data(self.index)
        return getattr(iface, name)

    def __setattr__(self, name, value):
        if name[0] == '_': # forbid anything that doesn't start with a _
            super(Interface, self).__setattr__(name, value)
            return
        iface = interface(index = self.index)
        setattr(iface, name, value)
        return self._slave.set_if(iface)

    def add_v4_address(self, address, prefix_len, broadcast = None):
        addr = ipv4address(address, prefix_len, broadcast)
        self._slave.add_addr(self.index, addr)

    def add_v6_address(self, address, prefix_len):
        addr = ipv6address(address, prefix_len)
        self._slave.add_addr(self.index, addr)

    def del_v4_address(self, address, prefix_len, broadcast = None):
        addr = ipv4address(address, prefix_len, broadcast)
        self._slave.del_addr(self.index, addr)

    def del_v6_address(self, address, prefix_len):
        addr = ipv6address(address, prefix_len)
        self._slave.del_addr(self.index, addr)

    def get_addresses(self):
        addresses = self._slave.get_addr_data(self.index)
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

class NodeInterface(NSInterface):
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
        self._control = SlaveInterface(ctl.index)
        super(NodeInterface, self).__init__(node, ns.index)

    @property
    def control(self):
        return self._control

    def destroy(self):
        try:
            self._slave.del_if(self.index)
        except:
            # Maybe it already went away, or the slave died. Anyway, better
            # ignore the error
            pass

class P2PInterface(NSInterface):
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
        super(P2PInterface, o1).__init__(node1, pair[0].index)

        o2 = P2PInterface.__new__(P2PInterface)
        super(P2PInterface, o2).__init__(node2, pair[1].index)

        return o1, o2

    def __init__(self):
        "Not to be called directly. Use P2PInterface.create_pair()"
        raise RuntimeError(P2PInterface.__init__.__doc__)

    def destroy(self):
        try:
            self._slave.del_if(self.index)
        except:
            pass

class ForeignNodeInterface(NSInterface):
    """Class to handle already existing interfaces inside a name space, usually
    just the loopback device, but it can be other user-created interfaces. On
    destruction, the code will try to restore the interface to the state it was
    in before being imported into netns."""
    def __init__(self, node, iface):
        iface = node._slave.get_if_data(iface)
        self._original_state = iface
        super(ForeignNodeInterface, self).__init__(node, iface.index)

    # FIXME: register somewhere for destruction!
    def destroy(self): # override: restore as much as possible
        try:
            self._slave.set_if(self._original_state)
        except:
            pass

class ExternalInterface(Interface):
    """Add user-facing methods for interfaces that run in the main namespace."""
    @property
    def control(self):
        # This is *the* control interface
        return self

    # some black magic to automatically get/set interface attributes
    def __getattr__(self, name):
        iface = netns.iproute.get_if(self.index)
        return getattr(iface, name)

    def __setattr__(self, name, value):
        if name[0] == '_': # forbid anything that doesn't start with a _
            super(ExternalInterface, self).__setattr__(name, value)
            return
        iface = interface(index = self.index)
        setattr(iface, name, value)
        return netns.iproute.set_if(iface)

    def add_v4_address(self, address, prefix_len, broadcast = None):
        addr = ipv4address(address, prefix_len, broadcast)
        netns.iproute.add_addr(self.index, addr)

    def add_v6_address(self, address, prefix_len):
        addr = ipv6address(address, prefix_len)
        netns.iproute.add_addr(self.index, addr)

    def del_v4_address(self, address, prefix_len, broadcast = None):
        addr = ipv4address(address, prefix_len, broadcast)
        netns.iproute.del_addr(self.index, addr)

    def del_v6_address(self, address, prefix_len):
        addr = ipv6address(address, prefix_len)
        netns.iproute.del_addr(self.index, addr)

    def get_addresses(self):
        addresses = netns.iproute.get_addr_data(self.index)
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

class SlaveInterface(ExternalInterface):
    """Class to handle the main-name-space-facing couples of Nodeinterface.
    Does nothing, just avoids any destroy code."""
    def destroy(self):
        pass

class ForeignInterface(ExternalInterface):
    """Class to handle already existing interfaces. This kind of interfaces can
    only be connected to Link objects and not assigned to a name space.
    On destruction, the code will try to restore the interface to the state it
    was in before being imported into netns."""
    def __init__(self, iface):
        iface = netns.iproute.get_if(iface)
        self._original_state = iface
        super(ForeignInterface, self).__init__(iface.index)

    # FIXME: register somewhere for destruction!
    def destroy(self): # override: restore as much as possible
        try:
            netns.iproute.set_if(self._original_state)
        except:
            pass

# Link is just another interface type

class Link(ExternalInterface):
    @staticmethod
    def _gen_br_name():
        n = Link._gen_next_id()
        # Max 15 chars
        return "NETNSbr-%.4x%.3x" % (os.getpid(), n)

    def __init__(self, bandwidth = None, delay = None, delay_jitter = None,
            delay_correlation = None, delay_distribution = None, loss = None,
            loss_correlation = None, dup = None, dup_correlation = None,
            corrupt = None, corrupt_correlation = None):

        self._bandwidth = bandwidth
        self._delay = delay
        self._delay_jitter = delay_jitter
        self._delay_correlation = delay_correlation
        self._delay_distribution = delay_distribution
        self._loss = loss
        self._loss_correlation = loss_correlation
        self._dup = dup
        self._dup_correlation = dup_correlation
        self._corrupt = corrupt
        self._corrupt_correlation = corrupt_correlation

        iface = netns.iproute.create_bridge(self._gen_br_name())
        super(Link, self).__init__(iface.index)

        self._ports = set()
        # FIXME: is this correct/desirable/etc?
        self.stp = False
        self.forward_delay = 0
        # FIXME: register somewhere

    def __getattr__(self, name):
        iface = netns.iproute.get_bridge(self.index)
        return getattr(iface, name)

    def __setattr__(self, name, value):
        if name[0] == '_': # forbid anything that doesn't start with a _
            super(ExternalInterface, self).__setattr__(name, value)
            return
        iface = bridge(index = self.index)
        setattr(iface, name, value)
        return netns.iproute.set_bridge(iface)

    def __del__(self):
        self.destroy()

    def destroy(self):
        for p in self._ports:
            try:
                self.disconnect(p)
            except:
                pass
        self.up = False
        netns.iproute.del_bridge(self.index)

    def connect(self, iface):
        assert iface.control.index not in self._ports
        netns.iproute.add_bridge_port(self.index, iface.control.index)
        # FIXME: up/down, mtu, etc should be automatically propagated?
        iface.control.up = True
        self._ports.add(iface.control.index)

    def disconnect(self, iface):
        assert iface.control.index in self._ports
        netns.iproute.del_bridge_port(self.index, iface.control.index)
        self._ports.remove(iface.control.index)


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
        self._index     = _positive(index) if index is not None else None
        self.name       = name
        self.up         = up
        self.mtu        = mtu
        self.lladdr     = lladdr
        self.broadcast  = broadcast
        self.multicast  = multicast
        self.arp        = arp

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
        name        = None if self.name == o.name else self.name
        up          = None if self.up == o.up else self.up
        mtu         = None if self.mtu == o.mtu else self.mtu
        lladdr      = None if self.lladdr == o.lladdr else self.lladdr
        broadcast   = None if self.broadcast == o.broadcast else self.broadcast
        multicast   = None if self.multicast == o.multicast else self.multicast
        arp         = None if self.arp == o.arp else self.arp
        return self.__class__(self.index, name, up, mtu, lladdr, broadcast,
                multicast, arp)

class bridge(interface):
    changeable_attributes = interface.changeable_attributes + ["stp",
            "forward_delay", "hello_time", "ageing_time", "max_age"]

    # Index should be read-only
    stp = property(_make_getter("_stp"), _make_setter("_stp", _any_to_bool))
    forward_delay = property(_make_getter("_forward_delay"),
            _make_setter("_forward_delay", float))
    hello_time = property(_make_getter("_hello_time"),
            _make_setter("_hello_time", float))
    ageing_time = property(_make_getter("_ageing_time"),
            _make_setter("_ageing_time", float))
    max_age = property(_make_getter("_max_age"),
            _make_setter("_max_age", float))

    @classmethod
    def upgrade(cls, iface, *kargs, **kwargs):
        """Upgrade a interface to a bridge."""
        return cls(iface.index, iface.name, iface.up, iface.mtu, iface.lladdr,
                iface.broadcast, iface.multicast, iface.arp, *kargs, **kwargs)

    def __init__(self, index = None, name = None, up = None, mtu = None,
            lladdr = None, broadcast = None, multicast = None, arp = None,
            stp = None, forward_delay = None, hello_time = None,
            ageing_time = None, max_age = None):
        super(bridge, self).__init__(index, name, up, mtu, lladdr, broadcast,
                multicast, arp)
        self.stp            = stp
        self.forward_delay  = forward_delay
        self.hello_time     = hello_time
        self.ageing_time    = ageing_time
        self.max_age        = max_age

    def __repr__(self):
        s = "%s.%s(index = %s, name = %s, up = %s, mtu = %s, lladdr = %s, "
        s += "broadcast = %s, multicast = %s, arp = %s, stp = %s, "
        s += "forward_delay = %s, hello_time = %s, ageing_time = %s, "
        s += "max_age = %s)"
        return s % (self.__module__, self.__class__.__name__,
                self.index.__repr__(), self.name.__repr__(),
                self.up.__repr__(), self.mtu.__repr__(),
                self.lladdr.__repr__(), self.broadcast.__repr__(),
                self.multicast.__repr__(), self.arp.__repr__(),
                self.stp.__repr__(), self.forward_delay.__repr__(),
                self.hello_time.__repr__(), self.ageing_time.__repr__(),
                self.max_age.__repr__())

    def __sub__(self, o):
        r = super(bridge, self).__sub__(o)
        if type(o) == interface:
            return r
        r.stp           = None if self.stp == o.stp else self.stp
        r.hello_time    = None if self.hello_time == o.hello_time else \
                self.hello_time
        r.forward_delay = None if self.forward_delay == o.forward_delay else \
                self.forward_delay
        r.ageing_time   = None if self.ageing_time == o.ageing_time else \
                self.ageing_time
        r.max_age       = None if self.max_age == o.max_age else self.max_age
        return r

class address(object):
    """Class for internal use. It is mostly a data container used to easily
    pass information around; with some convenience methods. __eq__ and __hash__
    are defined just to be able to easily find duplicated addresses."""
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

