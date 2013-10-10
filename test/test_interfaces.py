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

class TestIPRouteStuff(unittest.TestCase):
    def test_fix_lladdr(self):
        fl = nemu.iproute._fix_lladdr
        self.assertEquals(fl('42:71:e0:90:ca:42'), '42:71:e0:90:ca:42')
        self.assertEquals(fl('4271E090CA42'), '42:71:e0:90:ca:42',
                'Normalization of link-level address: missing colons and '
                'upper caps')
        self.assertEquals(fl('2:71:E:90:CA:42'), '02:71:0e:90:ca:42',
                'Normalization of link-level address: missing zeroes')
        self.assertEquals(fl('271E090CA42'), '02:71:e0:90:ca:42',
                'Automatic normalization of link-level address: missing '
                'colons and zeroes')
        self.assertRaises(ValueError, fl, 'foo')
        self.assertRaises(ValueError, fl, '42:71:e0:90:ca42')
        self.assertRaises(ValueError, fl, '1234567890123')
 
    def test_any_to_bool(self):
        a2b = nemu.iproute._any_to_bool
        for i in (True, 2, 'trUe', '1', 'foo', 1.0, [1]):
            self.assertTrue(a2b(i))
        for i in (False, 0, 'falsE', '0', '', 0.0, []):
            self.assertFalse(a2b(i))

    def test_non_empty_str(self):
        nes = nemu.iproute._non_empty_str
        self.assertEquals(nes(''), None)
        self.assertEquals(nes('Foo'), 'Foo')
        self.assertEquals(nes(1), '1')

    def test_interface(self):
        i = nemu.iproute.interface(index = 1)
        self.assertRaises(AttributeError, setattr, i, 'index', 2)
        self.assertRaises(ValueError, setattr, i, 'mtu', -1)
        self.assertEquals(repr(i), 'nemu.iproute.interface(index = 1, '
                'name = None, up = None, mtu = None, lladdr = None, '
                'broadcast = None, multicast = None, arp = None)')
        i.name = 'foo'; i.up = 1; i.arp = True; i.mtu = 1500
        self.assertEquals(repr(i), 'nemu.iproute.interface(index = 1, '
                'name = \'foo\', up = True, mtu = 1500, lladdr = None, '
                'broadcast = None, multicast = None, arp = True)')
        j = nemu.iproute.interface(index = 2)
        j.name = 'bar'; j.up = False; j.arp = 1
        # Modifications to turn j into i.
        self.assertEquals(repr(i - j), 'nemu.iproute.interface(index = 1, '
                'name = \'foo\', up = True, mtu = 1500, lladdr = None, '
                'broadcast = None, multicast = None, arp = None)')
        # Modifications to turn i into j.
        self.assertEquals(repr(j - i), 'nemu.iproute.interface(index = 2, '
                'name = \'bar\', up = False, mtu = None, lladdr = None, '
                'broadcast = None, multicast = None, arp = None)')

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
        r = node0.system([IP_PATH, "link", "set", if0.name, "mtu", "1500"])
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
                    (IP_PATH, self.dummyname)), 0)
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
            os.system("%s link del %s" % (IP_PATH, self.dummyname))

# FIXME: Links

if __name__ == '__main__':
    unittest.main()

