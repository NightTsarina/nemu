#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import unittest
import netns
import os

class TestInterfaces(unittest.TestCase):
#    def setUp(self):
#        pass
    def test_interfaces(self):
        node0 = netns.Node()
        if0 = a.add_if(mac_address = '42:71:e0:90:ca:42', mtu = 1492)
        self.assertEquals(if0.mac_address, '42:71:e0:90:ca:42')
        if0.mac_address = '4271E090CA42'
        self.assertEquals(if0.mac_address, '42:71:e0:90:ca:42')
        self.assertRaises(BaseException, setattr, if0, 'mac_address', 'foo')
        self.assertRaises(BaseException, setattr, if0, 'mac_address',
                '12345678901')
        self.assertEquals(if0.mtu, 1492)
        self.assertRaises(BaseException, setattr, if0, 'mtu', 0)
        self.assertRaises(BaseException, setattr, if0, 'mtu', 65537)

        # FIXME: run-time tests

        dummyname = "dummy%d" % os.getpid()
        self.assertEquals(
                os.system("ip link add name %s type dummy" % dummyname), 0)
        if1 = a.import_if(dummyname)

if __name__ == '__main__':
    unittest.main()

