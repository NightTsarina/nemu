#/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4
import netns
import signal

# run_as: user to setuid() to before running applications (this is assumed to
# roon as root)
netns.config.run_as = 'nobody'

# Clean-up is essential to avoid leaving bridge devices all over the place
# (luckily, the veths die automatically). This installs signals and exit
# handlers.
netns.set_cleanup_hooks(on_exit = True,
        on_signals = [signal.SIGTERM, signal.SIGINT])

# each Node is a netns
a = netns.Node()
b = netns.Node()
print "Nodes started with pids: %d and %d" % (a.pid, b.pid)

# interface object maps to a veth pair with one end in a netns
# XXX: should it be named lladdr instead?
if0 = a.add_if(mac_address = '42:71:e0:90:ca:42')
if1 = b.add_if(mtu = 1492)
# for using with a tun device, to connect to the outside world
if2 = b.import_if('tun0')

# each Link is a linux bridge, all the parameters are applied to the associated
# interfaces as tc qdiscs.
link0 = netns.Link(bandwidth = 100 * 1024 * 1024,
        delay = 0.01, delay_jitter = 0.001,
        delay_correlation = 0.25, delay_distribution = 'normal',
        loss = 0.005, loss_correlation = 0.20,
        dup = 0.005, dup_correlation = 0.25,
        corrupt = 0.005, corrupt_correlation = 0.25)

# connect to the bridge
link0.connect(if0)
link0.connect(if1)
#link0.connect(if2)

# Should be experimented with Tom Geoff's patch to see if the bridge could be
# avoided; but for that the API would be slightly different, as these would be
# point-to-point interfaces and links.
# ppp0 = netns.PPPLink(a, b, bandwidth = ....)
# if0 = ppp0.interface(a)

# Add and connect a tap device (as if a external router were plugged into a
# switch)
link0.add_tunnel_if()

link0.enabled = True
if0.enabled = True
if1.enabled = True

# addresses as iproute
if0.add_v4_address(addr = '10.0.0.1', prefix_len = 24)
if0.add_v6_address(addr = 'fe80::222:19ff:fe22:615d', prefix_len = 64)
if1.add_v4_address(addr = '10.0.0.2', prefix_len = 24,
        broadcast = '10.1.0.255')

# ditto
#a.add_route(prefix = '0', prefix_len = 0, nexthop = '10.0.0.2')
a.add_default_route(nexthop = '10.0.0.2')
b.add_route(prefix = '10.1.0.0', prefix_len = 16, nexthop = '10.0.0.1')
b.add_route(prefix = '11.1.0.1', prefix_len = 32, device = if1)

# Some inspection methods: they will not read internal data but query the
# kernel
addrs = if0.get_addresses()
stats = if0.get_stats()
routes = a.get_routes()
ifaces = a.get_interfaces()
nodes = netns.get_nodes()
links = netns.get_links()
stats = link0.get_stats()

# IDEA: implement Node.popen and build the others upon it.
# IDEA: use SCM_RIGHTS to pass filedescriptors instead of using pipes/sockets

# Run a process in background, associate its stdio to three named pipes
app0 = a.start_process("ping -c 3 10.0.0.2")
print "ping command PIPES at (%s, %s, %s)" % app0.pipes
app0.kill(15)

# The same, but directly as python file objects
app1 = a.start_process(["ping", "-c", "3", "10.0.0.2"])
buf = app1.stdout.read()
app1.wait()

# Run, capture output and wait()
(stdout, stderr) = a.run_process(["ping", "-c", "3", "10.0.0.2"])
# stdout, stderr are strings

# Run an process with a pseudo-tty associated to it; provide a UNIX socket to
# interact with the process
app2 = a.start_tty_process("/bin/bash")
# app2.sockname, app2.sockfd
app2.wait()

# Example to set up a linear topology
def setup_linear_topology(n, bd, delay):
    nodes = []
    for i in range(n):
        nodes.append(netns.Node())

    for i in range(n - 1):
        if1 = nodes[i].add_if()
        if2 = nodes[i + 1].add_if()
        if1.add_v4_address(addr = ('10.0.%d.2' % i), prefix_len = 24)
        if2.add_v4_address(addr = ('10.0.%d.1' % i), prefix_len = 24)
        link = netns.Link(bandwidth = bd, delay = delay)
        link.connect(if1)
        link.connect(if2)

    for i in range(n):
        for j in range(n):
            if abs(i - j) <= 1:
                continue
            nodes[i].add_route(prefix = ('10.0.%d.0' % j), prefix_len = 24,
                    nexthop = ('10.0.%d.%d' % ((i, 1) if i < j else (i - 1, 2)))
                    )
    return nodes

