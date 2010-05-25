#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import netns
import os
import re
import subprocess
import unittest

def process_ipcmd(str):
    cur = None
    out = {}
    for line in str.split("\n"):
        if line == "":
            cur = None
            continue
        match = re.search(r'^(\d+): (\S+): <(\S+)> mtu (\d+) qdisc (\S+)',
                line)
        if match != None:
            cur = match.group(2)
            out[cur] = {
                    'idx':      match.group(1),
                    'flags':    match.group(3).split(","),
                    'mtu':      match.group(4),
                    'qdisc':    match.group(5),
                    'addr':     []
                    }
            out[cur]['up'] = 'UP' in out[cur]['flags']
            continue
        # Assume cur is defined
        assert cur != None
        match = re.search(r'^\s+link/\S* ([0-9a-f:]+)(?: |$)', line)
        if match != None:
            out[cur]['lladdr'] = match.group(1)
            continue

        match = re.search(r'^\s+inet ([0-9.]+)/(\d+)(?: brd ([0-9.]+))?', line)
        if match != None:
            out[cur]['addr'].append({
                'addr': match.group(1),
                'plen': int(match.group(2)),
                'bcast': match.group(3),
                'family': 'inet'})
            continue

        match = re.search(r'^\s+inet6 ([0-9a-f:]+)/(\d+)(?: |$)', line)
        if match != None:
            out[cur]['addr'].append({
                'addr': match.group(1),
                'plen': int(match.group(2)),
                'family': 'inet6'})
            continue

        match = re.search(r'^\s{6}', line)
        assert match != None
    return out

def get_devs():
    ipcmd = subprocess.Popen(["ip", "addr", "list"],
            stdout = subprocess.PIPE)
    (outdata, errdata) = ipcmd.communicate()
    ipcmd.wait()
    return process_ipcmd(outdata)

def get_devs_netns(node):
    (outdata, errdata) = node.run_process(["ip", "addr", "list"])
    return process_ipcmd(outdata)

class TestInterfaces(unittest.TestCase):
    def test_util(self):
        devs = get_devs()
        # There should be at least loopback!
        self.assertTrue(len(devs) > 0)
        self.assertTrue('lo' in devs)
        self.assertTrue(devs['lo']['up'])
        self.assertEquals(devs['lo']['lladdr'], '00:00:00:00:00:00')
        self.assertTrue( {
            'addr': '127.0.0.1', 'plen': 8,
            'bcast': None, 'family': 'inet'
            } in devs['lo']['addr'])

    def test_interface_creation(self):
        node0 = netns.Node()
        ifaces = []
        for i in range(5):
            ifaces.append(node0.add_if())

        devs = get_devs_netns(node0)
        for i in range(5):
            self.assertFalse(devs['lo']['up'])
            self.assertTrue(ifaces[i].name in devs)

        devs = get_devs()
        for i in range(5):
            self.assertTrue(ifaces[i].peer_name in devs)

        self.assertEquals(set(ifaces), node0.get_interfaces())

    def test_interface_settings(self):
        node0 = netns.Node()
        if0 = node0.add_if(mac_address = '42:71:e0:90:ca:42', mtu = 1492)
        self.assertEquals(if0.mac_address, '42:71:e0:90:ca:42')
        if0.mac_address = '4271E090CA42'
        self.assertEquals(if0.mac_address, '42:71:e0:90:ca:42')
        self.assertRaises(BaseException, setattr, if0, 'mac_address', 'foo')
        self.assertRaises(BaseException, setattr, if0, 'mac_address',
                '12345678901')
        self.assertEquals(if0.mtu, 1492)
        self.assertRaises(BaseException, setattr, if0, 'mtu', 0)
        self.assertRaises(BaseException, setattr, if0, 'mtu', 65537)

        devs = get_devs_netns(node0)
        self.assertTrue(if0.name in devs)
        self.assertFalse(devs[if0.name]['up'])
        self.assertEquals(devs[if0.name]['lladdr'], if0.mac_address)
        self.assertEquals(devs[if0.name]['mtu'], if0.mtu)

        if0.enable = True
        devs = get_devs_netns(node0)
        self.assertTrue(devs[if0.name]['up'])

        # Verify that data is actually read from the kernel
        node0.run_process(["ip", "link", "set", if0.name, "mtu", "1500"])
        devs = get_devs_netns(node0)
        self.assertEquals(devs[if0.name]['mtu'], 1500)
        self.assertEquals(devs[if0.name]['mtu'], if0.mtu)

        # FIXME: get_stats

    def test_interface_migration(self):
        node0 = netns.Node()
        dummyname = "dummy%d" % os.getpid()
        self.assertEquals(
                os.system("ip link add name %s type dummy" % dummyname), 0)
        devs = get_devs()
        self.assertTrue(dummyname in devs)

        if0 = node0.import_if(dummyname)
        if0.mac_address = '42:71:e0:90:ca:43'
        if0.mtu = 1400

        devs = get_devs_netns(node0)
        self.assertTrue(if0.name in devs)
        self.assertEquals(devs[if0.name]['lladdr'], if0.mac_address)
        self.assertEquals(devs[if0.name]['mtu'], if0.mtu)

    def test_interface_addresses(self):
        node0 = netns.Node()
        if0 = node0.add_if()
        if0.add_v4_address(addr = '10.0.0.1', prefix_len = 24,
                broadcast = '10.0.0.255')
        if0.add_v4_address(addr = '10.0.2.1', prefix_len = 26)
        if0.add_v6_address(addr = 'fe80::222:19ff:fe22:615d', prefix_len = 64)

        devs = get_devs_netns(node0)
        self.assertTrue( {
            'addr': '10.0.0.1', 'plen': 24,
            'bcast': '10.0.0.255', 'family': 'inet'
            } in devs[if0.name]['addr'])
        self.assertTrue( {
            'addr': '10.0.2.1', 'plen': 26,
            'bcast': None, 'family': 'inet'
            } in devs[if0.name]['addr'])
        self.assertTrue( {
            'addr': 'fe80::222:19ff:fe22:615d', 'plen': 64,
            'bcast': None, 'family': 'inet6'
            } in devs[if0.name]['addr'])

        # FIXME: proper tests when I decide on the data format
        self.assertTrue(len(if0.get_addresses()) >= 2)

# FIXME: Links

if __name__ == '__main__':
    unittest.main()

