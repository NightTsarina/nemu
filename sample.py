#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4
import netns, subprocess

# each Node is a netns
node0 = netns.Node()
node1 = netns.Node()
node2 = netns.Node()
print "Nodes started with pids: %s" % str((node0.pid, node1.pid,
    node2.pid))

# interface object maps to a veth pair with one end in a netns
if0  = netns.NodeInterface(node0)
if1a = netns.NodeInterface(node1)
# Between node1 and node2, we use a P2P interface
(if1b, if2) = netns.P2PInterface.create_pair(node1, node2)

switch0 = netns.Switch(
        bandwidth = 100 * 1024 * 1024,
        delay = 0.01, # 10 ms
        delay_jitter = 0.001, # 1ms
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

# RFC-4193 Unique local addresses.
# Pre-generated random block: fde2:4a1d:8870::/48
if0.add_v6_address(address = 'fde2:4a1d:8870:0::1',
        prefix_len = 32)
if1a.add_v6_address(address = 'fde2:4a1d:8870:0::2',
        prefix_len = 32)
if1b.add_v6_address(address = 'fde2:4a1d:8870:1::1',
        prefix_len = 32)
if2.add_v6_address(address = 'fde2:4a1d:8870:1::2',
        prefix_len = 32)

# Configure routing
node0.add_route(prefix = '10.0.1.0', prefix_len = 24,
        nexthop = '10.0.0.2')
node2.add_route(prefix = '10.0.0.0', prefix_len = 24,
        nexthop = '10.0.1.1')

node0.add_route(prefix = 'fde2:4a1d:8870:1::', prefix_len = 32,
        nexthop = 'fde2:4a1d:8870:0::1')
node2.add_route(prefix = 'fde2:4a1d:8870:0::', prefix_len = 32,
        nexthop = 'fde2:4a1d:8870:1::0')

# Test connectivity first. Run process, hide output and check
# return code
null = file("/dev/null", "w")
app0 = node0.Popen("ping -c 1 10.0.1.2", shell = True,
        stdout = null)
ret = app0.wait()
assert ret == 0

app1 = node2.Popen("ping -c 1 10.0.0.1", shell = True,
        stdout = null)
ret = app1.wait()
assert ret == 0
print "Connectivity IPv4 OK!"

# if arguments speficied as array, no need to invoke the shell
app2 = node0.Popen(["ping6", "-c1", "fde2:4a1d:8870:1::2"])#, stdout = null)
ret = app2.wait()
#assert ret == 0

app3 = node0.Popen(["ping6", "-c1", "fde2:4a1d:8870:0::1"], stdout = null)
ret = app3.wait()
#assert ret == 0
print "Connectivity IPv6 OK!"
