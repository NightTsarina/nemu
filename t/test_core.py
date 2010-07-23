#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import grp, os, pwd, time, unittest
import netns, test_util

class TestConfigure(unittest.TestCase):
    def test_config_run_as_static(self):
        # Don't allow root as default user
        self.assertRaises(AttributeError, setattr, netns.config,
                'run_as', 'root')
        self.assertRaises(AttributeError, setattr, netns.config,
                'run_as', 0)
        # Don't allow invalid users
        self.assertRaises(AttributeError, setattr, netns.config,
                'run_as', 'foobarbaz') # hope nobody has this user!
        self.assertRaises(AttributeError, setattr, netns.config,
                'run_as', -1)

class TestGlobal(unittest.TestCase):
    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_run_ping(self):
        n1 = netns.Node()
        n2 = netns.Node()
        i1, i2 = netns.P2PInterface.create_pair(n1, n2)
        i1.up = i2.up = True
        i1.lladdr = 'd6:4b:3f:f7:ff:7e'
        i2.lladdr = 'd6:4b:3f:f7:ff:7f'
        i1.add_v4_address('10.0.0.1', 24)
        i2.add_v4_address('10.0.0.2', 24)

        null = file('/dev/null', 'wb')
        a1 = n1.Popen(['ping', '-qc1', '10.0.0.2'], stdout = null)
        a2 = n2.Popen(['ping', '-qc1', '10.0.0.1'], stdout = null)
        self.assertEquals(a1.wait(), 0)
        self.assertEquals(a2.wait(), 0)

        # Test ipv6 autoconfigured addresses
        time.sleep(2) # Wait for autoconfiguration
        a1 = n1.Popen(['ping6', '-qc1', '-I', i1.name,
            'fe80::d44b:3fff:fef7:ff7f'], stdout = null)
        a2 = n2.Popen(['ping6', '-qc1', '-I', i2.name,
            'fe80::d44b:3fff:fef7:ff7e'], stdout = null)
        self.assertEquals(a1.wait(), 0)
        self.assertEquals(a2.wait(), 0)

    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_run_ping_bridging(self):
        n1 = netns.Node()
        n2 = netns.Node()
        i1 = n1.add_if()
        i2 = n2.add_if()
        i1.up = i2.up = True
        l = netns.Link()
        l.connect(i1)
        l.connect(i2)
        l.up = True
        i1.add_v4_address('10.0.0.1', 24)
        i2.add_v4_address('10.0.0.2', 24)

        null = file('/dev/null', 'wb')
        a1 = n1.Popen(['ping', '-qc1', '10.0.0.2'], stdout = null)
        a2 = n2.Popen(['ping', '-qc1', '10.0.0.1'], stdout = null)
        self.assertEquals(a1.wait(), 0)
        self.assertEquals(a2.wait(), 0)

if __name__ == '__main__':
    unittest.main()
