#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import unittest
import netns
import os
import re
import subprocess

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
                'plen': match.group(2),
                'bcast': match.group(3),
                'family': 'inet'})
            continue

        match = re.search(r'^\s+inet6 ([0-9a-f:]+)/(\d+)(?: |$)', line)
        if match != None:
            out[cur]['addr'].append({
                'addr': match.group(1),
                'plen': match.group(2),
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
        self.assertEquals(devs['lo']['lladdr'], '00:00:00:00:00:00')

    def test_interfaces(self):
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
        self.assertEquals(devs[if0.name]['lladdr'], if0.mac_address)
        self.assertEquals(devs[if0.name]['mtu'], if0.mtu)

        dummyname = "dummy%d" % os.getpid()
        self.assertEquals(
                os.system("ip link add name %s type dummy" % dummyname), 0)
        devs = get_devs()
        self.assertTrue(dummyname in devs)

        if1 = node0.import_if(dummyname)
        if1.mac_address = '42:71:e0:90:ca:43'
        if1.mtu = 1400

        devs = get_devs_netns(node0)
        self.assertTrue(if1.name in devs)
        self.assertEquals(devs[if1.name]['lladdr'], if1.mac_address)
        self.assertEquals(devs[if1.name]['mtu'], if1.mtu)

if __name__ == '__main__':
    unittest.main()

