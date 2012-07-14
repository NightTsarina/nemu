#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4
import os, nemu, subprocess, time

xterm = nemu.environ.find_bin("xterm")
mtr = nemu.environ.find_bin("mtr")
X = "DISPLAY" in os.environ and xterm

# Do not use X stuff.
X = False

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
        switch[-1].connect(iface[(i, i - 1)])
        switch[-1].connect(iface[(i - 1, i)])
        switch[-1].up = True
    # Configure routing
    for j in range(SIZE - 1):
        if j in (i, i - 1):
            continue
        if j < i:
            node[i].add_route(prefix='10.0.%d.0' % j, prefix_len=24,
                    nexthop='10.0.%d.1' % (i - 1))
        else:
            node[i].add_route(prefix='10.0.%d.0' % j, prefix_len=24,
                    nexthop='10.0.%d.2' % i)

print "Nodes started with pids: %s" % str([n.pid for n in node])

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
    app = []
    for i in range(SIZE - 1):
        height = 102
        base = 25
        cmd = "%s -eni %s" % (nemu.environ.TCPDUMP_PATH, iface[(i, i + 1)].name)
        xtermcmd = "%s -geometry 100x5+0+%d -T %s -e %s" % (
                xterm, i * height + base, "node%d" % i, cmd)
        app.append(node[i].Popen(xtermcmd, shell=True))

    app.append(node[-1].Popen("%s -n 10.0.0.1" % mtr, shell=True))
    app[-1].wait()
    for i in range(SIZE - 1):
        app[i].signal()
        app[i].wait()
else:
    node[-1].system("%s -n --report 10.0.0.1" % mtr)
