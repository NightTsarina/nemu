#!/usr/bin/env python
# vim: ts=4:sw=4:et:ai:sts=4

import getopt, netns, os.path, re, sys

__doc__ = """Creates a linear network topology, and measures the maximum
end-to-end throughput for the specified packet size."""

def usage(f):
    f.write("Usage: %s --nodes=<n> --pktsize=<n> [OPTIONS]\n\n%s\n\n" %
            (os.path.basename(sys.argv[0]), __doc__))
    f.write("Mandatory arguments:\n")
    f.write("  -n, --nodes=NODES        Number of nodes to create\n")
    f.write("  -s, --pktsize=BYTES      Size of packet payload\n\n")

    f.write("Topology configuration:\n")
    f.write("  --use-p2p                Use P2P links, to avoid bridging\n")
    f.write("  --delay=SECS             Add delay emulation in links\n")
    f.write("  --jitter=PERCENT         Add jitter emulation in links\n")
    f.write("  --bandwidth=BPS          Maximum bandwidth of links\n\n")

    f.write("How long should the benchmark run (defaults to -t 10):\n")
    f.write("  -t, --time=SECS          Stop after SECS seconds\n")
    f.write("  -p, --packets=NUM        Stop after NUM packets\n")
    f.write("  -b, --bytes=BYTES        Stop after BYTES bytes sent\n")

def main():
    error = None
    opts = []
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hn:s:t:p:b:", [
            "help", "nodes=", "pktsize=", "time=", "packets=", "bytes=",
            "use-p2p", "delay=", "jitter=", "bandwidth=" ])
    except getopt.GetoptError, err:
        error = str(err) # opts will be empty

    pktsize = nr = time = packets = bytes = None
    use_p2p = False
    delay = jitter = bandwidth = None

    for o, a in opts:
        if o in ("-h", "--help"):
            usage(sys.stdout)
            sys.exit(0)
        elif o in ("-n", "--nodes"):
            nr = int(a)
        elif o in ("-s", "--pktsize"):
            pktsize = int(a)
        elif o in ("-t", "--time"):
            time = float(a)
        elif o in ("-p", "--packets"):
            packets = int(a)
        elif o in ("--bytes"):
            bytes = int(a)
        elif o in ("--delay"):
            delay = float(a)
        elif o in ("--jitter"):
            jitter = float(a)
        elif o in ("--bandwidth"):
            bandwidth = float(a)
        elif o in ("--use-p2p"):
            use_p2p = True
            continue # avoid the value check
        else:
            raise RuntimeError("Cannot happen")
        # In all cases, I take a number
        if float(a) <= 0:
            error = "Invalid value for %s: %s" % (o, a)

    if not error:
        if args:
            error = "Unknown argument(s): %s" % " ".join(args)
        elif not nr:
            error = "Missing mandatory --nodes argument"
        elif not pktsize:
            error = "Missing mandatory --pktsize argument"
        elif use_p2p and (delay or jitter or bandwidth):
            error = "Cannot use link emulation with P2P links"

    if error:
        sys.stderr.write("%s: %s\n\n" % (os.path.basename(sys.argv[0]), error))
        usage(sys.stderr)
        sys.exit(2)

    if not (time or bytes or packets):
        time = 10

    nodes, interfaces, links = create_topo(nr, use_p2p, delay, jitter,
            bandwidth)

    #nodes[0].system("ping -c 30 -i 1.2 -w 60 -s 1400 %s" % dec2ip(ip2dec("10.0.0.2") + 4 * (nr - 2)))
    p=nodes[0].Popen(["iperf", "-s", "-u"])
    nodes[nr-1].system("iperf -c 10.0.0.1 -u -b 10000M")
    p.signal()
    p.wait()

def ip2dec(ip):
    match = re.search(r'^(\d+)\.(\d+)\.(\d+)\.(\d+)$', ip)
    assert match
    return long(match.group(1)) * 2**24 + long(match.group(2)) * 2**16 + \
            long(match.group(3)) * 2**8  + long(match.group(4))

def dec2ip(dec):
    res = [None] * 4
    for i in range(4):
        res[3 - i] = dec % 256
        dec >>= 8
    return "%d.%d.%d.%d" % tuple(res)

def create_topo(n, p2p, delay, jitter, bw):
    nodes = []
    interfaces = []
    links = []
    for i in range(n):
        nodes.append(netns.Node())
    if p2p:
        interfaces = [[None]]
        for i in range(n - 1):
            a, b = netns.P2PInterface.create_pair(nodes[i], nodes[i + 1])
            interfaces[i].append(a)
            interfaces.append([])
            interfaces[i + 1] = [b]
        interfaces[n - 1].append(None)
    else:
        for i in range(n):
            if i > 0:
                left = nodes[i].add_if()
            else:
                left = None
            if i < n - 1:
                right = nodes[i].add_if()
            else:
                right = None
            interfaces.append((left, right))
        for i in range(n - 1):
            link = netns.Link(bandwidth = bw, delay = delay,
                    delay_jitter = jitter)
            link.up = True
            link.connect(interfaces[i][1])
            link.connect(interfaces[i + 1][0])
            links.append(link)

    for i in range(n):
        for j in (0, 1):
            if interfaces[i][j]:
                interfaces[i][j].up = True

    ip = ip2dec("10.0.0.1")
    for i in range(n - 1):
        interfaces[i][1].add_v4_address(dec2ip(ip), 30)
        interfaces[i + 1][0].add_v4_address(dec2ip(ip + 1), 30)
        ip += 4

    ipbase = ip2dec("10.0.0.0")
    lastnet = dec2ip(ipbase + 4 * (n - 2))
    for i in range(n - 2):
        nodes[i].add_route(prefix = lastnet, prefix_len = 30,
                nexthop = dec2ip(ipbase + 4 * i + 2))
        nodes[n - 1 - i].add_route(prefix = "10.0.0.0", prefix_len = 30,
                nexthop = dec2ip(ipbase + (n - 2 - i) * 4 + 1))
    return nodes, interfaces, links

if __name__ == "__main__":
    main()
