#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

from test_util import get_devs, get_devs_netns
from nemu.environ import *
import nemu, test_util
import os, unittest

class TestUtils(unittest.TestCase):
    def test_utils(self):
        devs = get_devs()
        # There should be at least loopback!
        self.assertTrue(len(devs) > 0)
        self.assertTrue('lo' in devs)
        self.assertTrue(devs['lo']['up'])
        self.assertEquals(devs['lo']['lladdr'], '00:00:00:00:00:00')
        self.assertTrue( {
            'address': '127.0.0.1', 'prefix_len': 8,
            'broadcast': None, 'family': 'inet'
            } in devs['lo']['addr'])

class TestInterfaces(unittest.TestCase):
    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_interface_creation(self):
        node0 = nemu.Node()
        ifaces = []
        for i in range(5):
            ifaces.append(node0.add_if())

        devs = get_devs_netns(node0)
        for i in range(5):
            self.assertTrue(devs['lo']['up'])
            self.assertTrue(ifaces[i].name in devs)

        node_devs = set(node0.get_interfaces())
        self.assertTrue(set(ifaces).issubset(node_devs))
        loopback = node_devs - set(ifaces) # should be!
        self.assertEquals(len(loopback), 1)
        self.assertEquals(loopback.pop().name, 'lo')

        devs = get_devs()
        for i in range(5):
            peer_name = nemu.iproute.get_if(ifaces[i].control.index).name
            self.assertTrue(peer_name in devs)

    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_interface_settings(self):
        node0 = nemu.Node()
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
        r = node0.system([ip_path, "link", "set", if0.name, "mtu", "1500"])
        self.assertEquals(r, 0)
        devs = get_devs_netns(node0)
        self.assertEquals(devs[if0.name]['mtu'], 1500)
        self.assertEquals(devs[if0.name]['mtu'], if0.mtu)

        # FIXME: get_stats

    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_interface_addresses(self):
        node0 = nemu.Node()
        if0 = node0.add_if()
        if0.add_v4_address(address = '10.0.0.1', prefix_len = 24,
                broadcast = '10.0.0.255')
        if0.add_v4_address(address = '10.0.2.1', prefix_len = 26)
        if0.add_v6_address(address = 'fe80::222:19ff:fe22:615d',
                prefix_len = 64)

        devs = get_devs_netns(node0)
        self.assertTrue( {
            'address': '10.0.0.1', 'prefix_len': 24,
            'broadcast': '10.0.0.255', 'family': 'inet'
            } in devs[if0.name]['addr'])
        self.assertTrue( {
            'address': '10.0.2.1', 'prefix_len': 26,
            'broadcast': '10.0.2.63', 'family': 'inet'
            } in devs[if0.name]['addr'])
        self.assertTrue( {
            'address': 'fe80::222:19ff:fe22:615d', 'prefix_len': 64,
            'family': 'inet6'
            } in devs[if0.name]['addr'])

        self.assertTrue(len(if0.get_addresses()) >= 2)
        self.assertEquals(if0.get_addresses(), devs[if0.name]['addr'])

class TestWithDummy(unittest.TestCase):
    def setUp(self):
        self.cleanup = []

    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    @test_util.skipUnless(
            test_util.get_linux_ver() >= test_util.make_linux_ver("2.6.35"),
            "Test trigger a kernel bug on 2.6.34")
    def test_interface_migration(self):
        node = nemu.Node()
        self.dummyname = "dummy%d" % os.getpid()
        self.assertEquals(os.system("%s link add name %s type dummy" %
                    (ip_path, self.dummyname)), 0)
        devs = get_devs()
        self.assertTrue(self.dummyname in devs)
        dummyidx = devs[self.dummyname]['idx']

        if0 = node.import_if(self.dummyname)
        self.assertTrue(self.dummyname not in get_devs())

        node_devs = dict([(i.index, i) for i in node.get_interfaces()])
        self.assertTrue(dummyidx in node_devs)

        if0.lladdr = '42:71:e0:90:ca:43'
        if0.mtu = 1400

        devs = get_devs_netns(node)
        self.assertTrue(if0.name in devs)
        self.assertEquals(devs[if0.name]['lladdr'], '42:71:e0:90:ca:43')
        self.assertEquals(devs[if0.name]['mtu'], 1400)

        node.destroy()
        self.assertTrue(self.dummyname in get_devs())

    def tearDown(self):
        # oops here
        if hasattr(self, 'dummyname'):
            os.system("%s link del %s" % (ip_path, self.dummyname))

# FIXME: Links

if __name__ == '__main__':
    unittest.main()

