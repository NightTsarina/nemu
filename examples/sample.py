#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4
import os, nemu, subprocess, time

xterm = nemu.environ.find_bin("xterm")
X = "DISPLAY" in os.environ and xterm

# each Node is a netns
node0 = nemu.Node(forward_X11 = X)
node1 = nemu.Node(forward_X11 = X)
node2 = nemu.Node(forward_X11 = X)
print "Nodes started with pids: %s" % str((node0.pid, node1.pid,
    node2.pid))

# interface object maps to a veth pair with one end in a netns
if0  = nemu.NodeInterface(node0)
if1a = nemu.NodeInterface(node1)
# Between node1 and node2, we use a P2P interface
(if1b, if2) = nemu.P2PInterface.create_pair(node1, node2)

switch0 = nemu.Switch(
        bandwidth = 100 * 1024 * 1024,
        delay = 0.1, # 100 ms
        delay_jitter = 0.01, # 10ms
        delay_correlation = 0.25, # 25% correlation
        loss = 0.005)

# connect the interfaces
switch0.connect(if0)
switch0.connect(if1a)

# bring the interfaces up
switch0.up = if0.up = if1a.up = if1b.up = if2.up = True

# Add IP addresses
if0.add_v4_address(address = '10.0.0.1', prefix_len = 24)
if1a.add_v4_address(address = '10.0.0.2', prefix_len = 24)
if1b.add_v4_address(address = '10.0.1.1', prefix_len = 24)
if2.add_v4_address(address = '10.0.1.2', prefix_len = 24)

# Configure routing
node0.add_route(prefix = '10.0.1.0', prefix_len = 24, nexthop = '10.0.0.2')
node2.add_route(prefix = '10.0.0.0', prefix_len = 24, nexthop = '10.0.1.1')

# Test connectivity first. Run process, hide output and check
# return code
null = file("/dev/null", "w")
app0 = node0.Popen("ping -c 1 10.0.1.2", shell = True, stdout = null)
ret = app0.wait()
assert ret == 0

app1 = node2.Popen("ping -c 1 10.0.0.1", shell = True, stdout = null)
ret = app1.wait()
assert ret == 0
print "Connectivity IPv4 OK!"

if X:
    app1 = node1.Popen("%s -geometry -0+0 -e %s -ni %s" %
            (xterm, nemu.environ.tcpdump_path, if1b.name), shell = True)
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
