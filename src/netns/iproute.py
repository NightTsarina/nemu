# vim:ts=4:sw=4:et:ai:sts=4

import re, socket, subprocess, sys

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

    def __init__(self, index = None, name = None, up = None, mtu = None,
            lladdr = None, broadcast = None, multicast = None, arp = None):
        self.index = int(index) if index else None
        self.name = name
        self.up = up
        self.mtu = int(mtu) if mtu else None
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

    def __eq__(self, o):
        if not isinstance(o, address):
            return False
        return (self.family == o.family and self.address == o.address and
                self.prefix_len == o.prefix_len and
                self.broadcast == o.broadcast)

    def __hash__(self):
        h = (self.address.__hash__() ^ self.prefix_len.__hash__() ^
                self.family.__hash__())
        if hasattr(self, 'broadcast'):
            h ^= self.broadcast.__hash__()
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

# XXX: ideally this should be replaced by netlink communication
def get_if_data():
    """Gets current interface information. Returns a tuple (byidx, bynam) in
    which each element is a dictionary with the same data, but using different
    keys: interface indexes and interface names.

    In each dictionary, values are interface objects.
    """
    ipcmd = subprocess.Popen(["ip", "-o", "link", "list"],
        stdout = subprocess.PIPE)
    ipdata = ipcmd.communicate()[0]
    assert ipcmd.wait() == 0

    byidx = {}
    bynam = {}
    for line in ipdata.split("\n"):
        if line == "":
            continue
        match = re.search(r'^(\d+):\s+(.*)', line)
        idx = int(match.group(1))
        i = interface.parse_ip(line)
        byidx[idx] = bynam[i.name] = i
    return byidx, bynam

def get_addr_data():
    ipcmd = subprocess.Popen(["ip", "-o", "addr", "list"],
        stdout = subprocess.PIPE)
    ipdata = ipcmd.communicate()[0]
    assert ipcmd.wait() == 0

    byidx = {}
    bynam = {}
    for line in ipdata.split("\n"):
        if line == "":
            continue
        match = re.search(r'^(\d+):\s+(\S+?)(:?)\s+(.*)', line)
        if not match:
            raise RuntimeError("Invalid `ip' command output")
        idx = int(match.group(1))
        name = match.group(2)
        if match.group(3):
            continue # link info

        if name not in bynam:
            assert idx not in byidx
            bynam[name] = byidx[idx] = []
        bynam[name].append(address.parse_ip(match.group(4)))
    return byidx, bynam

def create_if_pair(if1, if2):
    assert if1.name and if2.name

    cmd = [[], []]
    iface = [if1, if2]
    for i in (0, 1):
        cmd[i] = ["name", iface[i].name]
        if iface[i].lladdr:
            cmd[i] += ["address", iface[i].lladdr]
        if iface[i].broadcast:
            cmd[i] += ["broadcast", iface[i].broadcast]
        if iface[i].mtu:
            cmd[i] += ["mtu", str(iface[i].mtu)]

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
    cmds = []
    if diff.name:
        cmds.append(_ils + ["name", diff.name])
    if diff.mtu:
        cmds.append(_ils + ["mtu", str(diff.mtu)])
    if diff.lladdr:
        cmds.append(_ils + ["address", diff.lladdr])
    if diff.broadcast:
        cmds.append(_ils + ["broadcast", diff.broadcast])
    if diff.up != None:
        cmds.append(_ils + ["up" if diff.up else "down"])
    if diff.multicast != None:
        cmds.append(_ils + ["multicast", "on" if diff.multicast else "off"])
    if diff.arp != None:
        cmds.append(_ils + ["arp", "on" if diff.arp else "off"])

    #print cmds
    for c in cmds:
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

# Useful stuff

def execute(cmd):
    print " ".join(cmd)#; return
    null = open('/dev/null', 'r+')
    p = subprocess.Popen(cmd, stdout = null, stderr = subprocess.PIPE)
    out, err = p.communicate()
    if p.returncode != 0:
        raise RuntimeError("Error executing `%s': %s" % (" ".join(cmd), err))

def get_real_if(iface):
    ifdata = get_if_data()
    if isinstance(iface, interface):
        if iface.index != None:
            return ifdata[0][iface.index]
        else:
            return ifdata[1][iface.name]
    if isinstance(iface, int):
        return ifdata[0][iface]
    return ifdata[1][iface]


