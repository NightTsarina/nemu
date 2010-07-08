# vim:ts=4:sw=4:et:ai:sts=4

import re, socket, subprocess, sys

class interfaceflags(object):
    @classmethod
    def parse(cls, string):
        l = string.split(",")
        up          = "UP" in l
        no_carrier  = "NO_CARRIER" in l
        loopback    = "LOOPBACK" in l
        broadcast   = "BROADCAST" in l
        multicast   = "MULTICAST" in l
        return cls(up, no_carrier, loopback, broadcast, multicast)
    def __init__(self, up = None, no_carrier = None, loopback = None,
            broadcast = None, multicast = None):
        self.up         = up
        self.no_carrier = no_carrier
        self.loopback   = loopback
        self.broadcast  = broadcast
        self.multicast  = multicast
    def __repr__(self):
        s = "%s.%s(up = %s, no_carrier = %s, loopback = %s, broadcast = %s, "
        s += "multicast = %s)"
        return s % (self.__module__, self.__class__.__name__, self.up,
                self.no_carrier, self.loopback, self.broadcast, self.multicast)
    def __sub__(self, o):
        """Compare flags and return a new object with just the flags that
        differ set (with the value they have in self). The no-carrier,
        broadcast, and loopback flags are ignored"""
        up = None if self.up == o.up else self.up
        #no_carrier = (None if self.no_carrier == o.no_carrier else
        #        self.no_carrier)
        #loopback = None if self.loopback == o.loopback else self.loopback
        #broadcast = None if self.broadcast == o.broadcast else self.broadcast
        multicast = None if self.multicast == o.multicast else self.multicast
        return self.__class__(up, None, None, None, multicast)
    def __eq__(self, o):
        return (self.up == o.up and self.loopback == o.loopback and
                self.broadcast == o.broadcast and
                self.multicast == o.multicast)
        
class interface(object):
    def __init__(self, index = None, name = None, flags = None, mtu = None,
            qdisc = None, tipe = None, lladdr = None, broadcast = None,
            addresses = None):
        self.index = int(index) if index else None
        self.name = name
        self.flags = flags
        self.mtu = int(mtu) if mtu else None
        self.qdisc = qdisc
        self.type = tipe
        self.lladdr = lladdr
        self.broadcast = broadcast
        if addresses:
            self.addresses = addresses
        else:
            self.addresses = []

    def _set_addresses(self, value):
        if value == None:
            self._addresses = None
            return
        assert len(value) == len(set(value))
        self._addresses = list(value)

    def _get_addresses(self):
        if self._addresses != None:
            return list(self._addresses) # Copy, to make this inmutable

    addresses = property(_get_addresses, _set_addresses)

    def __repr__(self):
        s = "%s.%s(index = %s, name = %s, flags = %s, mtu = %s, qdisc = %s, "
        s += "tipe = %s, lladdr = %s, broadcast = %s, addresses = %s)"
        return s % (self.__module__, self.__class__.__name__,
                self.index.__repr__(), self.name.__repr__(),
                self.flags.__repr__(), self.mtu.__repr__(),
                self.qdisc.__repr__(), self.type.__repr__(),
                self.lladdr.__repr__(), self.broadcast.__repr__(),
                self.addresses.__repr__())

    def __sub__(self, o):
        """Compare attributes and return a new object with just the attributes
        that differ set (with the value they have in the first operand). The
        index remains equal to the first operand; type and qdisc are
        ignored."""
        name = None if self.name == o.name else self.name
        flags = None if self.flags == o.flags else self.flags - o.flags
        mtu = None if self.mtu == o.mtu else self.mtu
        lladdr = None if self.lladdr == o.lladdr else self.lladdr
        broadcast = None if self.broadcast == o.broadcast else self.broadcast
        addresses = None if self.addresses == o.addresses else self.addresses
        return self.__class__(self.index, name, flags, mtu, None, None,
                lladdr, broadcast, addresses)

class address(object):
    @property
    def address(self): return self._address
    @property
    def prefix_len(self): return self._prefix_len
    @property
    def family(self): return self._family

class ipv4address(address):
    def __init__(self, address, prefix_len, broadcast):
        self._address = address
        self._prefix_len = int(prefix_len)
        self._broadcast = broadcast
        self._family = socket.AF_INET

    @property
    def broadcast(self): return self._broadcast

    def __repr__(self):
        s = "%s.%s(address = %s, prefix_len = %d, broadcast = %s)"
        return s % (self.__module__, self.__class__.__name__,
                self.address.__repr__(), self.prefix_len,
                self.broadcast.__repr__())

    def __eq__(self, o):
        return (self.address == o.address and
                self.prefix_len == o.prefix_len and
                self.broadcast == o.broadcast)

    def __hash__(self):
        return (self._address.__hash__() ^ self._prefix_len.__hash__() ^
                self._family.__hash__()) ^ self._broadcast.__hash__()

class ipv6address(address):
    def __init__(self, address, prefix_len):
        self._address = address
        self._prefix_len = int(prefix_len)
        self._family = socket.AF_INET6

    def __repr__(self):
        s = "%s.%s(address = %s, prefix_len = %d)"
        return s % (self.__module__, self.__class__.__name__,
                self.address.__repr__(), self.prefix_len)

    def __eq__(self, o):
        return (self.address == o.address and self.prefix_len == o.prefix_len)

    def __hash__(self):
        return (self._address.__hash__() ^ self._prefix_len.__hash__() ^
                self._family.__hash__())

# XXX: ideally this should be replaced by netlink communication
def get_if_data():
    """Gets current interface and addresses information. Returns a tuple
    (byidx, bynam) in which each element is a dictionary with the same data,
    but using different keys: interface indexes and interface names.

    In each dictionary, values are interface objects.
    """
    ipcmd = subprocess.Popen(["ip", "-o", "addr", "list"],
        stdout = subprocess.PIPE)
    ipdata = ipcmd.communicate()[0]
    assert ipcmd.wait() == 0

    curidx = name = None
    byidx = {}
    bynam = {}
    for line in ipdata.split("\n"):
        if line == "":
            continue
        match = re.search(r'^(\d+):\s+(.*)', line)
        if curidx != int(match.group(1)):
            curidx = int(match.group(1))

            match = re.search(r'^(\d+): (\S+): <(\S+)> mtu (\d+) qdisc (\S+)' +
                    r'.*link/(\S+) ([0-9a-f:]+) brd ([0-9a-f:]+)', line)
            name = match.group(2)
            byidx[curidx] = bynam[name] = interface(
                    index   = curidx,
                    name    = name,
                    flags   = interfaceflags.parse(match.group(3)),
                    mtu     = match.group(4),
                    qdisc   = match.group(5),
                    tipe    = match.group(6),
                    lladdr  = match.group(7),
                    broadcast = match.group(8),
                    )
            continue

        # Assume curidx is defined
        assert curidx != None

        match = re.search(("^%s: %s" % (curidx, name)) + r'\s+(.*)$', line)
        line = match.group(1)

        match = re.search(r'^inet ([0-9.]+)/(\d+)(?: brd ([0-9.]+))?', line)
        if match != None:
            byidx[curidx].addresses += [ipv4address(
                address     = match.group(1),
                prefix_len  = match.group(2),
                broadcast   = match.group(3))]
            continue

        match = re.search(r'^inet6 ([0-9a-f:]+)/(\d+)', line)
        if match != None:
            byidx[curidx].addresses += [ipv6address(
                address     = match.group(1),
                prefix_len  = match.group(2))]
            continue
        raise RuntimeError("Problems parsing ip command output")
    return byidx, bynam

def create_if_pair(if1, if2):
    assert if1.name and if2.name

    cmd = [[], []]
    iface = [if1, if2]
    for i in (0, 1):
        cmd[i] = ["name", iface[i].name]
        if iface[i].lladdr:
            cmd[i].expand(["address", iface[i].lladdr])
        if iface[i].broadcast:
            cmd[i].expand(["broadcast", iface[i].broadcast])
        if iface[i].mtu:
            cmd[i].expand(["mtu", str(iface[i].mtu)])

    cmd = ["ip", "link", "add"] + cmd[0] + ["type", "veth", "peer"] + cmd[1]
    execute(cmd)
    try:
        set_if(if1)
        set_if(if2)
    except:
        (t, v, bt) = sys.exc_info()
        try:
            del_if(if1)
            del_if(if2)
        except:
            pass
        raise t, v, bt
    interfaces = get_if_data()[1]
    return interfaces[if1.name], interfaces[if2.name]

def del_if(iface):
    interface = get_real_if(iface)
    execute(["ip", "link", "del", interface.name])

def set_if(iface, recover = True):
    interface = get_real_if(iface)
    _ils = ["ip", "link", "set", "dev", interface.name]
    diff = iface - interface
    commands = []
    if diff.name:
        commands.append(_ils + ["name", diff.name])
    if diff.mtu:
        commands.append(_ils + ["mtu", str(diff.mtu)])
    if diff.lladdr:
        commands.append(_ils + ["address", diff.lladdr])
    if diff.broadcast:
        commands.append(_ils + ["broadcast", diff.broadcast])
    if diff.flags:
        if diff.flags.up != None:
            commands.append(_ils + ["up" if diff.flags.up else "down"])
        if diff.flags.multicast != None:
            commands.append(_ils + ["multicast",
                "on" if diff.flags.multicast else "off"])

    #print commands
    for c in commands:
        try:
            execute(c)
        except:
            if recover:
                set_if(interface, recover = False) # rollback
                raise

def add_addr(iface, address):
    interface = get_real_if(iface)
    assert address not in interface.addresses
    cmd = ["ip", "addr", "add", "dev", interface.name, "local",
            "%s/%d" % (address.address, int(address.prefix_len))]
    if hasattr(address, "broadcast"):
        cmd += ["broadcast", address.broadcast if address.broadcast else "+"]
    execute(cmd)
    interfaces = get_if_data()[0]
    return interfaces[iface.index]

def del_addr(iface, address):
    interface = get_real_if(iface)
    assert address in interface.addresses
    cmd = ["ip", "addr", "del", "dev", interface.name, "local",
            "%s/%d" % (address.address, int(address.prefix_len))]
    execute(cmd)
    interfaces = get_if_data()[0]
    return interfaces[iface.index]

def set_addr(iface, recover = True):
    interface = get_real_if(iface)
    to_remove = set(interface.addresses) - set(iface.addresses)
    to_add = set(iface.addresses) - set(interface.addresses)

    for a in to_remove:
        try:
            del_addr(iface, a)
        except:
            if recover:
                set_addr(interface, recover = False) # rollback
                raise

    for a in to_add:
        try:
            add_addr(iface, a)
        except:
            if recover:
                set_addr(interface, recover = False) # rollback
                raise
    return get_real_if(iface)

def execute(cmd):
    print " ".join(cmd)#; return
    null = open('/dev/null', 'r+')
    p = subprocess.Popen(cmd, stdout = null, stderr = subprocess.PIPE)
    out, err = p.communicate()
    if p.returncode != 0:
        raise RuntimeError("Error executing `%s': %s" % (" ".join(cmd), err))

def get_real_if(iface):
    if iface.index != None:
        return get_if_data()[0][iface.index]
    else:
        return get_if_data()[1][iface.name]

