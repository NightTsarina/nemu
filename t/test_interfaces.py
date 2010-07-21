#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

from test_util import get_devs, get_devs_netns
import netns, test_util
import os
import unittest

class TestUtils(unittest.TestCase):
    def test_utils(self):
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

class TestInterfaces(unittest.TestCase):
    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
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
            peer_name = netns.iproute.get_if(ifaces[i].control_index).name
            self.assertTrue(peer_name in devs)

        self.assertEquals(set(ifaces), set(node0.get_interfaces()))

    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_interface_settings(self):
        node0 = netns.Node()
        if0 = node0.add_if(lladdr = '42:71:e0:90:ca:42', mtu = 1492)
        self.assertEquals(if0.lladdr, '42:71:e0:90:ca:42',
                "Constructor parameters")
        self.assertEquals(if0.mtu, 1492, "Constructor parameters")
        if0.lladdr = '4271E090CA42'
        self.assertEquals(if0.lladdr, '42:71:e0:90:ca:42', """Normalization of
                link-level address: missing colons and upper caps""")
        if0.lladdr = '2:71:E0:90:CA:42'
        self.assertEquals(if0.lladdr, '02:71:e0:90:ca:42',
                """Normalization of link-level address: missing zeroes""")
        if0.lladdr = '271E090CA42'
        self.assertEquals(if0.lladdr, '02:71:e0:90:ca:42',
                """Automatic normalization of link-level address: missing
                colons and zeroes""")
        self.assertRaises(ValueError, setattr, if0, 'lladdr', 'foo')
        self.assertRaises(ValueError, setattr, if0, 'lladdr', '1234567890123')
        self.assertEquals(if0.mtu, 1492)
        # detected by setter
        self.assertRaises(ValueError, setattr, if0, 'mtu', 0)
        # error from ip
        self.assertRaises(RuntimeError, setattr, if0, 'mtu', 1)
        self.assertRaises(RuntimeError, setattr, if0, 'mtu', 65537)

        devs = get_devs_netns(node0)
        self.assertTrue(if0.name in devs)
        self.assertFalse(devs[if0.name]['up'])
        self.assertEquals(devs[if0.name]['lladdr'], if0.lladdr)
        self.assertEquals(devs[if0.name]['mtu'], if0.mtu)

        if0.up = True
        devs = get_devs_netns(node0)
        self.assertTrue(devs[if0.name]['up'])

        # Verify that data is actually read from the kernel
        r = node0.system(["ip", "link", "set", if0.name, "mtu", "1500"])
        self.assertEquals(r, 0)
        devs = get_devs_netns(node0)
        self.assertEquals(devs[if0.name]['mtu'], 1500)
        self.assertEquals(devs[if0.name]['mtu'], if0.mtu)

        # FIXME: get_stats

    #@test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    @test_util.skip("Not implemented")
    def test_interface_migration(self):
        node0 = netns.Node()
        dummyname = "dummy%d" % os.getpid()
        self.assertEquals(
                os.system("ip link add name %s type dummy" % dummyname), 0)
        devs = get_devs()
        self.assertTrue(dummyname in devs)

        if0 = node0.import_if(dummyname)
        if0.lladdr = '42:71:e0:90:ca:43'
        if0.mtu = 1400

        devs = get_devs_netns(node0)
        self.assertTrue(if0.name in devs)
        self.assertEquals(devs[if0.name]['lladdr'], if0.lladdr)
        self.assertEquals(devs[if0.name]['mtu'], if0.mtu)

    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_interface_addresses(self):
        node0 = netns.Node()
        if0 = node0.add_if()
        if0.add_v4_address(address = '10.0.0.1', prefix_len = 24,
                broadcast = '10.0.0.255')
        if0.add_v4_address(address = '10.0.2.1', prefix_len = 26)
        if0.add_v6_address(address = 'fe80::222:19ff:fe22:615d',
                prefix_len = 64)

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

