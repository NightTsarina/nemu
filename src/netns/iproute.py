# vim:ts=4:sw=4:et:ai:sts=4

import os, re, socket, subprocess, sys

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

# XXX: ideally this should be replaced by netlink communication

# helpers
def _execute(cmd):
    #print " ".join(cmd)#; return
    null = open('/dev/null', 'r+')
    p = subprocess.Popen(cmd, stdout = null, stderr = subprocess.PIPE)
    out, err = p.communicate()
    if p.returncode != 0:
        raise RuntimeError("Error executing `%s': %s" % (" ".join(cmd), err))

def _get_if_name(iface):
    if isinstance(iface, interface):
        if iface.name != None:
            return iface.name
    if isinstance(iface, str):
        return iface
    return get_if(iface).name

# Interface handling
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
        match = re.search(r'^(\d+): (\S+): <(\S+)> mtu (\d+) qdisc \S+' +
                r'.*link/\S+ ([0-9a-f:]+) brd ([0-9a-f:]+)', line)
        flags = match.group(3).split(",")
        i = interface(
                index   = match.group(1),
                name    = match.group(2),
                up      = "UP" in flags,
                mtu     = match.group(4),
                lladdr  = match.group(5),
                arp     = not ("NOARP" in flags),
                broadcast = match.group(6),
                multicast = "MULTICAST" in flags)
        byidx[idx] = bynam[i.name] = i
    return byidx, bynam

def get_if(iface):
    ifdata = get_if_data()
    if isinstance(iface, interface):
        if iface.index != None:
            return ifdata[0][iface.index]
        else:
            return ifdata[1][iface.name]
    if isinstance(iface, int):
        return ifdata[0][iface]
    return ifdata[1][iface]

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
    _execute(cmd)
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
    ifname = _get_if_name(iface)
    _execute(["ip", "link", "del", ifname])

def set_if(iface, recover = True):
    def do_cmds(cmds, orig_iface):
        for c in cmds:
            try:
                _execute(c)
            except:
                if recover:
                    set_if(orig_iface, recover = False) # rollback
                    raise

    orig_iface = get_if(iface)
    diff = iface - orig_iface # Only set what's needed

    # Name goes first
    if diff.name:
        _ils = ["ip", "link", "set", "dev"]
        cmds = [_ils + [orig_iface.name, "name", diff.name]]
        if orig_iface.up:
            # iface needs to be down
            cmds = [_ils + [orig_iface.name, "down"], cmds[0],
                    _ils + [diff.name, "up"]]
        do_cmds(cmds, orig_iface)

    # I need to use the new name after a name change, duh!
    _ils = ["ip", "link", "set", "dev", diff.name or orig_iface.name]
    cmds = []
    if diff.lladdr:
        if orig_iface.up:
            # iface needs to be down
            cmds.append(_ils + ["down"])
        cmds.append(_ils + ["address", diff.lladdr])
        if orig_iface.up and diff.up == None:
            # restore if it was up and it's not going to be set later
            cmds.append(_ils + ["up"])
    if diff.mtu:
        cmds.append(_ils + ["mtu", str(diff.mtu)])
    if diff.broadcast:
        cmds.append(_ils + ["broadcast", diff.broadcast])
    if diff.multicast != None:
        cmds.append(_ils + ["multicast", "on" if diff.multicast else "off"])
    if diff.arp != None:
        cmds.append(_ils + ["arp", "on" if diff.arp else "off"])
    if diff.up != None:
        cmds.append(_ils + ["up" if diff.up else "down"])

    do_cmds(cmds, orig_iface)

def change_netns(iface, netns):
    ifname = _get_if_name(iface)
    _execute(["ip", "link", "set", "dev", ifname, "netns", str(netns)])

# Address handling

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
            bynam[name] = byidx[idx] = []
            continue # link info
        bynam[name].append(_parse_ip_addr(match.group(4)))
    return byidx, bynam

def _parse_ip_addr(line):
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

def add_addr(iface, address):
    ifname = _get_if_name(iface)
    addresses = get_addr_data()[1][ifname]
    assert address not in addresses

    cmd = ["ip", "addr", "add", "dev", ifname, "local",
            "%s/%d" % (address.address, int(address.prefix_len))]
    if hasattr(address, "broadcast"):
        cmd += ["broadcast", address.broadcast if address.broadcast else "+"]
    _execute(cmd)

def del_addr(iface, address):
    ifname = _get_if_name(iface)
    addresses = get_addr_data()[1][ifname]
    assert address in addresses

    cmd = ["ip", "addr", "del", "dev", ifname, "local",
            "%s/%d" % (address.address, int(address.prefix_len))]
    _execute(cmd)

def set_addr(iface, addresses, recover = True):
    ifname = _get_if_name(iface)
    addresses = get_addr_data()[1][ifname]
    to_remove = set(orig_addresses) - set(addresses)
    to_add = set(addresses) - set(orig_addresses)

    for a in to_remove:
        try:
            del_addr(ifname, a)
        except:
            if recover:
                set_addr(orig_addresses, recover = False) # rollback
                raise

    for a in to_add:
        try:
            add_addr(ifname, a)
        except:
            if recover:
                set_addr(orig_addresses, recover = False) # rollback
                raise

# Bridge handling
def _sysfs_read_br(brname):
    def readval(fname):
        f = file(fname)
        return f.readline().strip()

    p = '/sys/class/net/%s/bridge/' % brname
    p2 = '/sys/class/net/%s/brif/' % brname
    try:
        os.stat(p)
    except:
        return None
    return dict(
            stp             = readval(p + 'stp_state'),
            forward_delay   = float(readval(p + 'forward_delay')) / 100,
            hello_time      = float(readval(p + 'hello_time')) / 100,
            ageing_time     = float(readval(p + 'ageing_time')) / 100,
            max_age         = float(readval(p + 'max_age')) / 100,
            ports           = os.listdir(p2))

def get_bridge_data():
    # brctl stinks too much; it is better to directly use sysfs, it is probably
    # stable by now
    byidx = {}
    bynam = {}
    ports = {}
    ifdata = get_if_data()
    for iface in ifdata[0].values():
        brdata = _sysfs_read_br(iface.name)
        if brdata == None:
            continue
        ports[iface.index] = [ifdata[1][x].index for x in brdata['ports']]
        del brdata['ports']
        bynam[iface.name] = byidx[iface.index] = \
                bridge.upgrade(iface, **brdata)
    return byidx, bynam, ports

def get_bridge(br):
    iface = get_if(br)
    brdata = _sysfs_read_br(iface.name)
    #ports = [ifdata[1][x].index for x in brdata['ports']]
    del brdata['ports']
    return bridge.upgrade(iface, **brdata)

def create_bridge(br):
    if isinstance(br, str):
        br = interface(name = br)
    assert br.name
    _execute(['brctl', 'addbr', br.name])
    try:
        set_if(br)
    except:
        (t, v, bt) = sys.exc_info()
        try:
            del_bridge(br)
        except:
            pass
        raise t, v, bt
    return get_if_data()[1][br.name]

def del_bridge(br):
    brname = _get_if_name(br)
    _execute(["brctl", "delbr", brname])

def set_bridge(br, recover = True):
    def saveval(fname, val):
        f = file(fname, 'w')
        f.write(str(val))
        f.close()
    def do_cmds(basename, cmds, orig_br):
        for n, v in cmds:
            try:
                saveval(basename + n, v)
            except:
                if recover:
                    set_bridge(orig_br, recover = False) # rollback
                    set_if(orig_br, recover = False) # rollback
                    raise

    orig_br = get_bridge(br)
    diff = br - orig_br # Only set what's needed

    cmds = []
    if diff.stp != None:
        cmds.append(('stp_state', int(diff.stp)))
    if diff.forward_delay != None:
        cmds.append(('forward_delay', int(diff.forward_delay)))
    if diff.hello_time != None:
        cmds.append(('hello_time', int(diff.hello_time)))
    if diff.ageing_time != None:
        cmds.append(('ageing_time', int(diff.ageing_time)))
    if diff.max_age != None:
        cmds.append(('max_age', int(diff.max_age)))

    set_if(diff)
    name = diff.name if diff.name != None else orig_br.name
    do_cmds('/sys/class/net/%s/bridge/' % name, cmds, orig_br)

def add_bridge_port(br, iface):
    ifname = _get_if_name(iface)
    brname = _get_if_name(br)
    _execute(['brctl', 'addif', brname, ifname])

def del_bridge_port(br, iface):
    ifname = _get_if_name(iface)
    brname = _get_if_name(br)
    _execute(['brctl', 'delif', brname, ifname])

def get_all_route_data():
    ipcmd = subprocess.Popen(["ip", "-o", "route", "list", "table", "all"],
        stdout = subprocess.PIPE)
    ipdata = ipcmd.communicate()[0]
    assert ipcmd.wait() == 0

    ifdata = get_if_data()[1]
    ret = []
    for line in ipdata.split("\n"):
        if line == "":
            continue
        match = re.match(r'(?:(unicast|local|broadcast|multicast|throw|' +
                r'unreachable|prohibit|blackhole|nat) )?' +
                r'(\S+)(?: via (\S+))? dev (\S+)', line)
        if not match:
            raise RuntimeError("Invalid output from `ip route'")
        type = match.group(1) or 'unicast'
        prefix = match.group(2)
        nexthop = match.group(3)
        device = ifdata[match.group(4)]
        if prefix == 'default' or re.search(r'/0$', prefix):
            prefix = None
        ret.append((type, prefix, nexthop, device))
    return ret
