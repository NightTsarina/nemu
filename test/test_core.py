#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import grp, os, pwd, time, threading, unittest
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
    def test_run_ping_p2pif(self):
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
    def test_run_ping_node_if(self):
        n1 = netns.Node()
        n2 = netns.Node()
        i1 = n1.add_if()
        i2 = n2.add_if()
        i1.up = i2.up = True
        l = netns.Switch()
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

    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_run_ping_routing(self):
        n1 = netns.Node()
        n2 = netns.Node()
        n3 = netns.Node()
        i1 = n1.add_if()
        i2a = n2.add_if()
        i2b = n2.add_if()
        i3 = n3.add_if()
        i1.up = i2a.up = i2b.up = i3.up = True
        l1 = netns.Switch()
        l2 = netns.Switch()
        l1.connect(i1)
        l1.connect(i2a)
        l2.connect(i2b)
        l2.connect(i3)
        l1.up = l2.up = True
        i1.add_v4_address('10.0.0.1', 24)
        i2a.add_v4_address('10.0.0.2', 24)
        i2b.add_v4_address('10.0.1.1', 24)
        i3.add_v4_address('10.0.1.2', 24)

        n1.add_route(prefix = '10.0.1.0', prefix_len = 24, nexthop = '10.0.0.2')
        n3.add_route(prefix = '10.0.0.0', prefix_len = 24, nexthop = '10.0.1.1')

        null = file('/dev/null', 'wb')
        a1 = n1.Popen(['ping', '-qc1', '10.0.1.2'], stdout = null)
        a2 = n3.Popen(['ping', '-qc1', '10.0.0.1'], stdout = null)
        self.assertEquals(a1.wait(), 0)
        self.assertEquals(a2.wait(), 0)


    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_run_ping_tap(self):
        """This test simulates a point to point connection between two hosts using two tap devices"""
        class ChannelThread:
            def __init__(self):
                self.stop = False
                self.thread = None

            def _run(self, fd1, fd2):
                while not self.stop:
                    s = os.read(fd1, 65536)
                    os.write(fd2, s)

            def start(self, fd1, fd2):
                self.thread = threading.Thread(target = self._run, args=[fd1, fd2])
                self.thread.start()
        
        n1 = netns.Node()
        n2 = netns.Node()

        i1 = n1.add_if()
        tap1 = n1.add_tap()
        tap2  = n2.add_tap()
        i2 = n2.add_if()
        i1.up = tap1.up = tap2.up = i2.up = True

        i1.add_v4_address('10.0.0.1', 24)
        tap1.add_v4_address('10.0.1.1', 24)
        tap2.add_v4_address('10.0.1.2', 24)
        i2.add_v4_address('10.0.2.2', 24)

        n2.add_route(prefix = '10.0.0.0', prefix_len = 24, nexthop = '10.0.1.2')
        n1.add_route(prefix = '10.0.2.0', prefix_len = 24, nexthop = '10.0.1.1')

        # communication forth between the two taps
        thread1 = ChannelThread()
        thread1.start(tap1.fd, tap2.fd)
        
        # communication back between the two taps
        thread2 = ChannelThread()
        thread2.start(tap2.fd, tap1.fd)

        null = file('/dev/null', 'wb')
        a = n1.Popen(['ping', '-qc1', '10.0.2.1'], stdout = null)
        self.assertEquals(a.wait(), 0)
        
        print 'jhola'

        thread1.stop = True
        thread2.stop = True

        os.write(tap1.fd, "0")
        os.write(tap2.fd, "0")

        thread1.thread.join()
        thread2.thread.join()
        print 'lalala'

if __name__ == '__main__':
    unittest.main()
