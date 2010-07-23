# vim:ts=4:sw=4:et:ai:sts=4

import os, re, subprocess, sys
import netns.interface

# XXX: ideally this should be replaced by netlink communication

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
        i = netns.interface.interface(
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
    if isinstance(iface, netns.interface.interface):
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

def get_br_data():
    # brctl stinks too much; it is better to directly use sysfs, it is probably
    # stable by now
    def readval(fname):
        f = file(fname)
        return f.readline().strip()

    byidx = {}
    bynam = {}
    ports = {}
    ifdata = get_if_data()
    for i in ifdata[1]: # by name
        p = '/sys/class/net/%s/bridge/' % i
        p2 = '/sys/class/net/%s/brif/' % i
        try:
            os.stat(p)
        except:
            continue
        params = dict(
                stp             = readval(p + 'stp_state'),
                forward_delay   = float(readval(p + 'forward_delay')) / 100,
                hello_time      = float(readval(p + 'hello_time')) / 100,
                ageing_time     = float(readval(p + 'ageing_time')) / 100,
                max_age         = float(readval(p + 'max_age')) / 100)
        iface = ifdata[1][i]
        bynam[i] = byidx[iface.index] = netns.interface.bridge.upgrade(
                iface, **params)
        ports[iface.index] = [ifdata[1][x].index for x in os.listdir(p2)]

    return byidx, bynam, ports

def create_bridge(br):
    if isinstance(br, str):
        br = netns.interface.interface(name = br)
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

    orig_br = get_br_data()[1][_get_if_name(br)]
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
    do_cmds('/sys/class/net/%s/bridge/' % br.name, cmds, orig_br)

def add_bridge_port(br, iface):
    ifname = _get_if_name(iface)
    brname = _get_if_name(br)
    _execute(['brctl', 'addif', brname, ifname])

def del_bridge_port(br, iface):
    ifname = _get_if_name(iface)
    brname = _get_if_name(br)
    _execute(['brctl', 'delif', brname, ifname])

# Useful stuff

def _execute(cmd):
    #print " ".join(cmd)#; return
    null = open('/dev/null', 'r+')
    p = subprocess.Popen(cmd, stdout = null, stderr = subprocess.PIPE)
    out, err = p.communicate()
    if p.returncode != 0:
        raise RuntimeError("Error executing `%s': %s" % (" ".join(cmd), err))

def _get_if_name(iface):
    if isinstance(iface, netns.interface.interface):
        if iface.name != None:
            return iface.name
    if isinstance(iface, str):
        return iface
    return get_if(iface).name
