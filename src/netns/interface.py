# vim:ts=4:sw=4:et:ai:sts=4

import re, socket

__all__ = ['interface', 'address', 'ipv6address', 'ipv4address']

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

class interface(object):
    @classmethod
    def parse_ip(cls, line):
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

    index = property(_make_getter("_index"), _make_setter("_index", int))
    up = property(_make_getter("_up"), _make_setter("_up", _any_to_bool))
    mtu = property(_make_getter("_mtu"), _make_setter("_mtu", int))
    arp = property(_make_getter("_arp"), _make_setter("_arp", _any_to_bool))
    multicast = property(_make_getter("_mc"), _make_setter("_mc", _any_to_bool))

    def __init__(self, index = None, name = None, up = None, mtu = None,
            lladdr = None, broadcast = None, multicast = None, arp = None):
        self.index = index
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
    @classmethod
    def parse_ip(cls, line):
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

