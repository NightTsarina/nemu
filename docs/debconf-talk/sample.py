#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4
import os, nemu, subprocess, time

xterm = nemu.environ.find_bin("xterm")
X = "DISPLAY" in os.environ and xterm

# each Node is a netns
node = []
switch = []
iface = {}
SIZE = 5
for i in range(SIZE):
    node.append(nemu.Node(forward_X11 = X))
    next_pair = (i, i + 1)
    prev_pair = (i, i - 1)
    if i < SIZE - 1:
        iface[(i, i + 1)] = nemu.NodeInterface(node[i])
        iface[(i, i + 1)].up = True
        iface[(i, i + 1)].add_v4_address(address='10.0.%d.1' % i, prefix_len=24)
    if i > 0:
        iface[(i, i - 1)] = nemu.NodeInterface(node[i])
        iface[(i, i - 1)].up = True
        iface[(i, i - 1)].add_v4_address(address='10.0.%d.2' % (i - 1),
                prefix_len=24)
        switch.append(nemu.Switch())
        switch[-1].connect(iface[(i, i - 1)], iface[(i - 1, i)])
        switch[-1].up = True
    # Configure routing
    if i < SIZE - 2:
        node[i].add_route(prefix='10.0.%d.0' % (SIZE - 2), prefix_len=24,
                nexthop='10.0.%d.2' % i)
    if i > 1:
        node[i].add_route(prefix='10.0.0.0', prefix_len=24,
                nexthop='10.0.%d.1' % i - 1)

print "Nodes started with pids: %s" % str([n.pid for n in nodes])

#switch0 = nemu.Switch(
#        bandwidth = 100 * 1024 * 1024,
#        delay = 0.1, # 100 ms
#        delay_jitter = 0.01, # 10ms
#        delay_correlation = 0.25, # 25% correlation
#        loss = 0.005)

# Test connectivity first. Run process, hide output and check
# return code
null = file("/dev/null", "w")
app0 = node[0].Popen("ping -c 1 10.0.%d.2" % (SIZE - 2), shell=True,
        stdout=null)
ret = app0.wait()
assert ret == 0

app1 = node[-1].Popen("ping -c 1 10.0.0.1", shell = True, stdout = null)
ret = app1.wait()
assert ret == 0
print "Connectivity IPv4 OK!"

if X:
    app1 = node1.Popen("%s -geometry -0+0 -e %s -ni %s" %
            (xterm, nemu.environ.TCPDUMP_PATH, if1b.name), shell = True)
    time.sleep(3)
    app0 = node0.Popen("%s -geometry +0+0 -e ping -c 10 10.0.1.2" % xterm,
            shell = True)
    app0.wait()
    app1.signal()
    app1.wait()

# Now test the network conditions
# When using a args list, the shell is not needed
app2 = node2.Popen(["ping", "-q", "-c100000", "-f", "10.0.1.2"],
        stdout = subprocess.PIPE)

out, err = app2.communicate()

print "Ping outout:"
print out
