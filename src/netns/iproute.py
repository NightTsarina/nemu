# vim:ts=4:sw=4:et:ai:sts=4

import re, subprocess, sys
import netns.interface

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
        i = netns.interface.interface.parse_ip(line)
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
        bynam[name].append(netns.interface.address.parse_ip(match.group(4)))
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
    orig_iface = get_if(iface)
    _ils = ["ip", "link", "set", "dev", orig_iface.name]
    diff = iface - orig_iface # Only set what's needed
    cmds = []
    if diff.name:
        cmds.append(_ils + ["name", diff.name])
    if diff.lladdr:
        cmds.append(_ils + ["address", diff.lladdr])
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
    
    # iface needs to be down before changing name or address
    if (diff.name or diff.lladdr) and orig_iface.up:
        cmds.insert(0, _ils + ["down"])
        if diff.up == None: # if it was not set already
            cmds.append(_ils + ["up"])

    #print cmds
    for c in cmds:
        try:
            _execute(c)
        except:
            if recover:
                set_if(orig_iface, recover = False) # rollback
                raise

def change_netns(iface, netns):
    ifname = _get_if_name(iface)
    _execute(["ip", "link", "set", "dev", ifname, "netns", str(netns)])

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

# Useful stuff

def _execute(cmd):
    print " ".join(cmd)#; return
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
