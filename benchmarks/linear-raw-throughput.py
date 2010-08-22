#!/usr/bin/env python
# vim: ts=4:sw=4:et:ai:sts=4

import csv, getopt, netns, os, os.path, re, select, subprocess, sys

__doc__ = """Creates a linear network topology, and measures the maximum
end-to-end throughput for the specified packet size."""

def usage(f):
    f.write("Usage: %s --nodes=NUM --pktsize=BYTES [OPTIONS]\n%s\n\n" %
            (os.path.basename(sys.argv[0]), __doc__))
    f.write("Mandatory arguments:\n")
    f.write("  -n, --nodes=NUM          Number of nodes to create\n")
    f.write("  -s, --pktsize=BYTES      Size of packet payload\n\n")

    f.write("Topology configuration:\n")
    f.write("  --use-p2p                Use P2P switchs, to avoid bridging\n")
    f.write("  --delay=SECS             Add delay emulation in switchs\n")
    f.write("  --jitter=PERCENT         Add jitter emulation in switchs\n")
    f.write("  --bandwidth=BPS          Maximum bandwidth of switchs\n\n")

    f.write("How long should the benchmark run (defaults to -t 10):\n")
    f.write("  -t, --time=SECS          Stop after SECS seconds\n")
    f.write("  -p, --packets=NUM        Stop after NUM packets\n")
    f.write("  -b, --bytes=BYTES        Stop after BYTES bytes sent\n\n")

    f.write("Output format:\n")
    f.write("  --format=FMT             Valid values are `csv', `brief', " +
            "and `verbose'\n")

def main():
    error = None
    opts = []
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hn:s:t:p:b:", [
            "help", "nodes=", "pktsize=", "time=", "packets=", "bytes=",
            "use-p2p", "delay=", "jitter=", "bandwidth=", "format=" ])
    except getopt.GetoptError, err:
        error = str(err) # opts will be empty

    pktsize = nr = time = packets = nbytes = None
    delay = jitter = bandwidth = None
    use_p2p = False
    format = "verbose"

    for o, a in opts:
        if o in ("-h", "--help"):
            usage(sys.stdout)
            sys.exit(0)
        elif o in ("-n", "--nodes"):
            nr = int(a)
            if nr > 65:
                error = "Invalid value for %s: %s" % (o, a)
                break
        elif o in ("-s", "--pktsize"):
            pktsize = int(a)
        elif o in ("-t", "--time"):
            time = float(a)
        elif o in ("-p", "--packets"):
            packets = int(a)
        elif o in ("--bytes"):
            nbytes = int(a)
        elif o in ("--delay"):
            delay = float(a)
        elif o in ("--jitter"):
            jitter = float(a)
        elif o in ("--bandwidth"):
            bandwidth = float(a)
        elif o in ("--use-p2p"):
            use_p2p = True
            continue # avoid the value check
        elif o == "--format":
            if a not in ('csv', 'brief', 'verbose'):
                error = "Invalid value for %s: %s" % (o, a)
                break
            format = a
            continue
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
            error = "Cannot use switch emulation with P2P switchs"

    if error:
        sys.stderr.write("%s: %s\n" % (os.path.basename(sys.argv[0]), error))
        sys.stderr.write("Try `%s --help' for more information.\n" %
                os.path.basename(sys.argv[0]))
        #usage(sys.stderr)
        sys.exit(2)

    if not (time or nbytes or packets):
        time = 10

    udp_perf = netns.environ.find_bin("udp-perf",
            extra_path = [".", os.path.dirname(sys.argv[0])])
    if not udp_perf:
        raise RuntimeError("Cannot find `udp-perf'")

    nodes, interfaces, switchs = create_topo(nr, use_p2p, delay, jitter,
            bandwidth)

    cmdline = [udp_perf, "--server"]
    if time:
        cmdline.append("--max-time=%d" % time)
    if packets:
        cmdline.append("--max-pkts=%d" % packets)
    if nbytes:
        cmdline.append("--max-bytes=%d" % nbytes)
    if format == "verbose":
        cmdline.append("--verbose")

    srv = nodes[0].Popen(cmdline, stdout = subprocess.PIPE)

    cmdline = [udp_perf, "--client", "--pktsize=%d" % pktsize]
    if nr > 1:
        cmdline.append("--host=10.0.0.1")
    clt = nodes[nr - 1].Popen(cmdline)

    out = ""
    while(True):
        ready = select.select([srv.stdout], [], [], 0.1)[0]
        if ready:
            r = os.read(srv.stdout.fileno(), 1024)
            if not r:
                break
            out += r
        if srv.poll() != None or clt.poll() != None:
            break

    if srv.poll():
        raise RuntimeError("upd-perf server returned with error.")

    if clt.poll():
        raise RuntimeError("upd-perf client returned with error.")

    srv.wait()
    clt.wait()

    out = out.strip()

    if format != "csv":
        print "Command line: %s" % (" ".join(sys.argv[1:]))
        print out.strip()
        return

    data = out.split(" ")
    data = dict(map(lambda s: s.partition(":")[::2], data))
    if sorted(data.keys()) != sorted(["brx", "prx", "pksz", "plsz", "err",
            "mind", "avgd", "maxd", "jit", "time"]):
        raise RuntimeError("Invalid output from udp-perf")
    data["nodes"] = nr
    data["bridge"] = int(not use_p2p)
    data["cfg_dly"] = delay if delay else ""
    data["cfg_bw"] = bandwidth if bandwidth else ""
    data["cfg_jit"] = jitter if jitter else ""

    res = []
    for i in ["nodes", "bridge", "cfg_dly", "cfg_bw", "cfg_jit",
            "brx", "prx", "pksz", "plsz", "err", "mind", "avgd",
            "maxd", "jit", "time"]:
        res.append(data[i])

    writer = csv.writer(sys.stdout)
    writer.writerow(res)

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
    switchs = []
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
            switch = netns.Switch(bandwidth = bw, delay = delay,
                    delay_jitter = jitter)
            switch.up = True
            switch.connect(interfaces[i][1])
            switch.connect(interfaces[i + 1][0])
            switchs.append(switch)

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
    return nodes, interfaces, switchs

if __name__ == "__main__":
    main()
