# vim:ts=4:sw=4:et:ai:sts=4

import copy, fcntl, os, re, socket, struct, subprocess, sys
from netns.environ import *

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

def _non_empty_str(val):
    if val == "":
        return None
    else:
        return str(val)

def _fix_lladdr(addr):
    foo = addr.lower()
    if ":" in addr:
        # Verify sanity and split
        m = re.search("^" + ":".join(["([0-9a-f]{1,2})"] * 6) + "$", foo)
        if m is None:
            raise ValueError("Invalid address: `%s'." % addr)
        # Fill missing zeros and glue again
        return ":".join(("0" * (2 - len(x)) + x for x in m.groups()))

    # Fill missing zeros
    foo = "0" * (12 - len(foo)) + foo
    # Verify sanity and split
    m = re.search("^" + "([0-9a-f]{2})" * 6 + "$", foo)
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

    def copy(self):
        return copy.copy(self)

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
    pass information around; with some convenience methods. __eq__ and
    __hash__ are defined just to be able to easily find duplicated
    addresses."""
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

class route(object):
    tipes = ["unicast", "local", "broadcast", "multicast", "throw",
            "unreachable", "prohibit", "blackhole", "nat"]

    tipe = property(_make_getter("_tipe", tipes.__getitem__),
            _make_setter("_tipe", tipes.index))
    prefix = property(_make_getter("_prefix"),
            _make_setter("_prefix", _non_empty_str))
    prefix_len = property(_make_getter("_plen"),
            lambda s, v: setattr(s, "_plen", int(v or 0)))
    nexthop = property(_make_getter("_nexthop"),
            _make_setter("_nexthop", _non_empty_str))
    interface = property(_make_getter("_interface"),
            _make_setter("_interface", _positive))
    metric = property(_make_getter("_metric"),
            lambda s, v: setattr(s, "_metric", int(v or 0)))

    def __init__(self, tipe = "unicast", prefix = None, prefix_len = 0,
            nexthop = None, interface = None, metric = 0):
        self.tipe = tipe
        self.prefix = prefix
        self.prefix_len = prefix_len
        self.nexthop = nexthop
        self.interface = interface
        self.metric = metric
        assert nexthop or interface

    def __repr__(self):
        s = "%s.%s(tipe = %s, prefix = %s, prefix_len = %s, nexthop = %s, "
        s += "interface = %s, metric = %s)"
        return s % (self.__module__, self.__class__.__name__,
                self.tipe.__repr__(), self.prefix.__repr__(),
                self.prefix_len.__repr__(), self.nexthop.__repr__(),
                self.interface.__repr__(), self.metric.__repr__())

    def __eq__(self, o):
        if not isinstance(o, route):
            return False
        return (self.tipe == o.tipe and self.prefix == o.prefix and
                self.prefix_len == o.prefix_len and self.nexthop == o.nexthop
                and self.interface == o.interface and self.metric == o.metric)

# helpers
def _get_if_name(iface):
    if isinstance(iface, interface):
        if iface.name != None:
            return iface.name
    if isinstance(iface, str):
        return iface
    return get_if(iface).name

# XXX: ideally this should be replaced by netlink communication
# Interface handling

# FIXME: try to lower the amount of calls to retrieve data!!
def get_if_data():
    """Gets current interface information. Returns a tuple (byidx, bynam) in
    which each element is a dictionary with the same data, but using different
    keys: interface indexes and interface names.

    In each dictionary, values are interface objects.
    """
    ipdata = backticks([ip_path, "-o", "link", "list"])

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

    cmd = [ip_path, "link", "add"] + cmd[0] + ["type", "veth", "peer"] + cmd[1]
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
    ifname = _get_if_name(iface)
    execute([ip_path, "link", "del", ifname])

def set_if(iface, recover = True):
    def do_cmds(cmds, orig_iface):
        for c in cmds:
            try:
                execute(c)
            except:
                if recover:
                    set_if(orig_iface, recover = False) # rollback
                    raise

    orig_iface = get_if(iface)
    diff = iface - orig_iface # Only set what's needed

    # Name goes first
    if diff.name:
        _ils = [ip_path, "link", "set", "dev"]
        cmds = [_ils + [orig_iface.name, "name", diff.name]]
        if orig_iface.up:
            # iface needs to be down
            cmds = [_ils + [orig_iface.name, "down"], cmds[0],
                    _ils + [diff.name, "up"]]
        do_cmds(cmds, orig_iface)

    # I need to use the new name after a name change, duh!
    _ils = [ip_path, "link", "set", "dev", diff.name or orig_iface.name]
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
    execute([ip_path, "link", "set", "dev", ifname, "netns", str(netns)])

# Address handling

def get_addr_data():
    ipdata = backticks([ip_path, "-o", "addr", "list"])

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

    cmd = [ip_path, "addr", "add", "dev", ifname, "local",
            "%s/%d" % (address.address, int(address.prefix_len))]
    if hasattr(address, "broadcast"):
        cmd += ["broadcast", address.broadcast if address.broadcast else "+"]
    execute(cmd)

def del_addr(iface, address):
    ifname = _get_if_name(iface)
    addresses = get_addr_data()[1][ifname]
    assert address in addresses

    cmd = [ip_path, "addr", "del", "dev", ifname, "local",
            "%s/%d" % (address.address, int(address.prefix_len))]
    execute(cmd)

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

    p = "/sys/class/net/%s/bridge/" % brname
    p2 = "/sys/class/net/%s/brif/" % brname
    try:
        os.stat(p)
    except:
        return None
    return dict(
            stp             = readval(p + "stp_state"),
            forward_delay   = float(readval(p + "forward_delay")) / 100,
            hello_time      = float(readval(p + "hello_time")) / 100,
            ageing_time     = float(readval(p + "ageing_time")) / 100,
            max_age         = float(readval(p + "max_age")) / 100,
            ports           = os.listdir(p2))

def get_bridge_data():
    # brctl stinks too much; it is better to directly use sysfs, it is
    # probably stable by now
    byidx = {}
    bynam = {}
    ports = {}
    ifdata = get_if_data()
    for iface in ifdata[0].values():
        brdata = _sysfs_read_br(iface.name)
        if brdata == None:
            continue
        ports[iface.index] = [ifdata[1][x].index for x in brdata["ports"]]
        del brdata["ports"]
        bynam[iface.name] = byidx[iface.index] = \
                bridge.upgrade(iface, **brdata)
    return byidx, bynam, ports

def get_bridge(br):
    iface = get_if(br)
    brdata = _sysfs_read_br(iface.name)
    #ports = [ifdata[1][x].index for x in brdata["ports"]]
    del brdata["ports"]
    return bridge.upgrade(iface, **brdata)

def create_bridge(br):
    if isinstance(br, str):
        br = interface(name = br)
    assert br.name
    execute([brctl_path, "addbr", br.name])
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
    execute([brctl_path, "delbr", brname])

def set_bridge(br, recover = True):
    def saveval(fname, val):
        f = file(fname, "w")
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
        cmds.append(("stp_state", int(diff.stp)))
    if diff.forward_delay != None:
        cmds.append(("forward_delay", int(diff.forward_delay)))
    if diff.hello_time != None:
        cmds.append(("hello_time", int(diff.hello_time)))
    if diff.ageing_time != None:
        cmds.append(("ageing_time", int(diff.ageing_time)))
    if diff.max_age != None:
        cmds.append(("max_age", int(diff.max_age)))

    set_if(diff)
    name = diff.name if diff.name != None else orig_br.name
    do_cmds("/sys/class/net/%s/bridge/" % name, cmds, orig_br)

def add_bridge_port(br, iface):
    ifname = _get_if_name(iface)
    brname = _get_if_name(br)
    execute([brctl_path, "addif", brname, ifname])

def del_bridge_port(br, iface):
    ifname = _get_if_name(iface)
    brname = _get_if_name(br)
    execute([brctl_path, "delif", brname, ifname])

# Routing

def get_all_route_data():
    ipdata = backticks([ip_path, "-o", "route", "list"]) # "table", "all"
    ipdata += backticks([ip_path, "-o", "-f", "inet6", "route", "list"])

    ifdata = get_if_data()[1]
    ret = []
    for line in ipdata.split("\n"):
        if line == "":
            continue
        match = re.match(r'(?:(unicast|local|broadcast|multicast|throw|' +
                r'unreachable|prohibit|blackhole|nat) )?' +
                r'(\S+)(?: via (\S+))? dev (\S+).*(?: metric (\d+))?', line)
        if not match:
            raise RuntimeError("Invalid output from `ip route': `%s'" % line)
        tipe = match.group(1) or "unicast"
        prefix = match.group(2)
        nexthop = match.group(3)
        interface = ifdata[match.group(4)]
        metric = match.group(5)
        if prefix == "default" or re.search(r'/0$', prefix):
            prefix = None
            prefix_len = 0
        else:
            match = re.match(r'([0-9a-f:.]+)(?:/(\d+))?$', prefix)
            prefix = match.group(1)
            prefix_len = int(match.group(2) or 32)
        ret.append(route(tipe, prefix, prefix_len, nexthop, interface.index,
            metric))
    return ret

def get_route_data():
    # filter out non-unicast routes
    return [x for x in get_all_route_data() if x.tipe == "unicast"]

def add_route(route):
    # Cannot really test this
    #if route in get_all_route_data():
    #    raise ValueError("Route already exists")
    _add_del_route("add", route)

def del_route(route):
    # Cannot really test this
    #if route not in get_all_route_data():
    #    raise ValueError("Route does not exist")
    _add_del_route("del", route)

def _add_del_route(action, route):
    cmd = [ip_path, "route", action]
    if route.tipe != "unicast":
        cmd += [route.tipe]
    if route.prefix:
        cmd += ["%s/%d" % (route.prefix, route.prefix_len)]
    else:
        cmd += ["default"]
    if route.nexthop:
        cmd += ["via", route.nexthop]
    if route.interface:
        cmd += ["dev", _get_if_name(route.interface)]
    execute(cmd)

# TC stuff

def get_tc_tree():
    tcdata = backticks([tc_path, "qdisc", "show"])

    data = {}
    for line in tcdata.split("\n"):
        if line == "":
            continue
        match = re.match(r'qdisc (\S+) ([0-9a-f]+):[0-9a-f]* dev (\S+) ' +
                r'(?:parent ([0-9a-f]+):[0-9a-f]*|root)\s*(.*)', line)
        if not match:
            raise RuntimeError("Invalid output from `tc qdisc': `%s'" % line)
        qdisc = match.group(1)
        handle = match.group(2)
        iface = match.group(3)
        parent = match.group(4) # or None
        extra = match.group(5)
        if iface not in data:
            data[iface] = {}
        if parent not in data[iface]:
            data[iface][parent] = []
        data[iface][parent] += [[handle, qdisc, parent, extra]]

    tree = {}
    for iface in data:
        def gen_tree(data, data_node):
            children = []
            node = {"handle": data_node[0],
                    "qdisc": data_node[1],
                    "extra": data_node[3],
                    "children": []}
            if data_node[0] in data:
                for h in data[data_node[0]]:
                    node["children"].append(gen_tree(data, h))
            return node
        tree[iface] = gen_tree(data[iface], data[iface][None][0])
    return tree

_multipliers = {"M": 1000000, "K": 1000}
_dividers = {"m": 1000, "u": 1000000}
def _parse_netem_delay(line):
    ret = {}
    match = re.search(r'delay ([\d.]+)([mu]?)s(?: +([\d.]+)([mu]?)s)?' +
            r'(?: *([\d.]+)%)?(?: *distribution (\S+))?', line)
    if not match:
        return ret

    delay = float(match.group(1))
    if match.group(2):
        delay /= _dividers[match.group(2)]
    ret["delay"] = delay

    if match.group(3):
        delay_jitter = float(match.group(3))
        if match.group(4):
            delay_jitter /= _dividers[match.group(4)]
        ret["delay_jitter"] = delay_jitter

    if match.group(5):
        ret["delay_correlation"] = float(match.group(5)) / 100

    if match.group(6):
        ret["delay_distribution"] = match.group(6)

    return ret

def _parse_netem_loss(line):
    ret = {}
    match = re.search(r'loss ([\d.]+)%(?: *([\d.]+)%)?', line)
    if not match:
        return ret

    ret["loss"] = float(match.group(1)) / 100
    if match.group(2):
        ret["loss_correlation"] = float(match.group(2)) / 100
    return ret

def _parse_netem_dup(line):
    ret = {}
    match = re.search(r'duplicate ([\d.]+)%(?: *([\d.]+)%)?', line)
    if not match:
        return ret

    ret["dup"] = float(match.group(1)) / 100
    if match.group(2):
        ret["dup_correlation"] = float(match.group(2)) / 100
    return ret

def _parse_netem_corrupt(line):
    ret = {}
    match = re.search(r'corrupt ([\d.]+)%(?: *([\d.]+)%)?', line)
    if not match:
        return ret

    ret["corrupt"] = float(match.group(1)) / 100
    if match.group(2):
        ret["corrupt_correlation"] = float(match.group(2)) / 100
    return ret

def get_tc_data():
    tree = get_tc_tree()
    ifdata = get_if_data()

    ret = {}
    for i in ifdata[0]:
        ret[i] = {"qdiscs": {}}
        if ifdata[0][i].name not in tree:
            continue
        node = tree[ifdata[0][i].name]
        if not node["children"]:
            if node["qdisc"] == "mq" or node["qdisc"] == "pfifo_fast" \
                    or node["qdisc"][1:] == "fifo":
                continue

            if node["qdisc"] == "netem":
                tbf = None
                netem = node["extra"], node["handle"]
            elif node["qdisc"] == "tbf":
                tbf = node["extra"], node["handle"]
                netem = None
            else:
                ret[i] = "foreign"
                continue
        else:
            if node["qdisc"] != "tbf" or len(node["children"]) != 1 or \
                    node["children"][0]["qdisc"] != "netem" or \
                    node["children"][0]["children"]:
                ret[i] = "foreign"
                continue
            tbf = node["extra"], node["handle"]
            netem = node["children"][0]["extra"], \
                    node["children"][0]["handle"]

        if tbf:
            ret[i]["qdiscs"]["tbf"] = tbf[1]
            match = re.search(r'rate (\d+)([MK]?)bit', tbf[0])
            if not match:
                ret[i] = "foreign"
                continue
            bandwidth = int(match.group(1))
            if match.group(2):
                bandwidth *= _multipliers[match.group(2)]
            ret[i]["bandwidth"] = bandwidth

        if netem:
            ret[i]["qdiscs"]["netem"] = netem[1]
            ret[i].update(_parse_netem_delay(netem[0]))
            ret[i].update(_parse_netem_loss(netem[0]))
            ret[i].update(_parse_netem_dup(netem[0]))
            ret[i].update(_parse_netem_corrupt(netem[0]))
    return ret, ifdata[0], ifdata[1]

def clear_tc(iface):
    iface = get_if(iface)
    tcdata = get_tc_data()[0]
    if tcdata[iface.index] == None:
        return
    # Any other case, we clean
    execute([tc_path, "qdisc", "del", "dev", iface.name, "root"])

def set_tc(iface, bandwidth = None, delay = None, delay_jitter = None,
        delay_correlation = None, delay_distribution = None,
        loss = None, loss_correlation = None,
        dup = None, dup_correlation = None,
        corrupt = None, corrupt_correlation = None):
    use_netem = bool(delay or delay_jitter or delay_correlation or
            delay_distribution or loss or loss_correlation or dup or
            dup_correlation or corrupt or corrupt_correlation)

    iface = get_if(iface)
    tcdata, ifdata = get_tc_data()[0:2]
    commands = []
    if tcdata[iface.index] == 'foreign':
        # Avoid the overhead of calling tc+ip again
        commands.append([tc_path, "qdisc", "del", "dev", iface.name, "root"])
        tcdata[iface.index] = {'qdiscs':  []}

    has_netem = 'netem' in tcdata[iface.index]['qdiscs']
    has_tbf = 'tbf' in tcdata[iface.index]['qdiscs']

    if not bandwidth and not use_netem:
        if has_netem or has_tbf:
            clear_tc(iface)
        return

    if has_netem == use_netem and has_tbf == bool(bandwidth):
        cmd = "change"
    else:
        # Too much work to do better :)
        if has_netem or has_tbf:
            commands.append([tc_path, "qdisc", "del", "dev", iface.name,
                "root"])
        cmd = "add"

    if bandwidth:
        rate = "%dbit" % int(bandwidth)
        mtu = ifdata[iface.index].mtu
        burst = max(mtu, int(bandwidth) / hz)
        limit = burst * 2 # FIXME?
        handle = "1:"
        if cmd == "change":
            handle = "%d:" % int(tcdata[iface.index]["qdiscs"]["tbf"])
        command = [tc_path, "qdisc", cmd, "dev", iface.name, "root", "handle",
                handle, "tbf", "rate", rate, "limit", str(limit), "burst",
                str(burst)]
        commands.append(command)

    if use_netem:
        handle = "2:"
        if cmd == "change":
            handle = "%d:" % int(tcdata[iface.index]["qdiscs"]["netem"])
        command = [tc_path, "qdisc", cmd, "dev", iface.name, "handle", handle]
        if bandwidth:
            parent = "1:"
            if cmd == "change":
                parent = "%d:" % int(tcdata[iface.index]["qdiscs"]["tbf"])
            command += ["parent", parent]
        else:
            command += ["root"]
        command += ["netem"]
        if delay:
            command += ["delay", "%fs" % delay]
            if delay_jitter:
                command += ["%fs" % delay_jitter]
            if delay_correlation:
                if not delay_jitter:
                    raise ValueError("delay_correlation requires delay_jitter")
                command += ["%f%%" % (delay_correlation * 100)]
            if delay_distribution:
                if not delay_jitter:
                    raise ValueError("delay_distribution requires delay_jitter")
                command += ["distribution", delay_distribution]
        if loss:
            command += ["loss", "%f%%" % (loss * 100)]
            if loss_correlation:
                command += ["%f%%" % (loss_correlation * 100)]
        if dup:
            command += ["duplicate", "%f%%" % (dup * 100)]
            if dup_correlation:
                command += ["%f%%" % (dup_correlation * 100)]
        if corrupt:
            command += ["corrupt", "%f%%" % (corrupt * 100)]
            if corrupt_correlation:
                command += ["%f%%" % (corrupt_correlation * 100)]
        commands.append(command)

    for c in commands:
        execute(c)

def create_tap(iface, use_pi = False):
    """Creates a tap device and returns the associated file descriptor"""
    if isinstance(iface, str):
        iface = interface(name = iface)
    assert iface.name

    IFF_TAP     = 0x0002
    IFF_NO_PI   = 0x1000
    TUNSETIFF   = 0x400454ca
    mode = IFF_TAP
    if not use_pi:
        mode |= IFF_NO_PI

    fd = os.open("/dev/net/tun", os.O_RDWR)

    err = fcntl.ioctl(fd, TUNSETIFF, struct.pack("16sH", iface.name, mode))
    if err < 0:
        os.close(fd)
        raise RuntimeError("Could not configure device %s" % iface.name)

    try:
        set_if(iface)
    except:
        os.close(fd)
        raise
    interfaces = get_if_data()[1]
    return interfaces[iface.name], fd

