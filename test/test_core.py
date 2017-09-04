#!/usr/bin/env python2
# vim:ts=4:sw=4:et:ai:sts=4

import grp, os, pwd, select, time, unittest
import nemu, test_util

class TestConfigure(unittest.TestCase):
    def test_config_run_as_static(self):
        # Don't allow root as default user
        self.assertRaises(AttributeError, setattr, nemu.config,
                'run_as', 'root')
        self.assertRaises(AttributeError, setattr, nemu.config,
                'run_as', 0)
        # Don't allow invalid users
        self.assertRaises(AttributeError, setattr, nemu.config,
                'run_as', 'foobarbaz') # hope nobody has this user!
        self.assertRaises(AttributeError, setattr, nemu.config,
                'run_as', 65536)
        try:
            pwd.getpwnam('nobody')
            nemu.config.run_as('nobody')
            self.assertEquals(nemu.config.run_as, 'nobody')
        except:
            pass

class TestGlobal(unittest.TestCase):
    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_run_ping_p2pif(self):
        n1 = nemu.Node()
        n2 = nemu.Node()
        i1, i2 = nemu.P2PInterface.create_pair(n1, n2)
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
        n1 = nemu.Node()
        n2 = nemu.Node()
        i1 = n1.add_if()
        i2 = n2.add_if()
        i1.up = i2.up = True
        l = nemu.Switch()
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
    def test_run_ping_routing_p2p(self):
        n1 = nemu.Node()
        n2 = nemu.Node()
        n3 = nemu.Node()
        i12, i21 = nemu.P2PInterface.create_pair(n1, n2)
        i23, i32 = nemu.P2PInterface.create_pair(n2, n3)
        i12.up = i21.up = i23.up = i32.up = True
        i12.add_v4_address('10.0.0.1', 24)
        i21.add_v4_address('10.0.0.2', 24)
        i23.add_v4_address('10.0.1.1', 24)
        i32.add_v4_address('10.0.1.2', 24)

        n1.add_route(prefix = '10.0.1.0', prefix_len = 24,
                nexthop = '10.0.0.2')
        n3.add_route(prefix = '10.0.0.0', prefix_len = 24,
                nexthop = '10.0.1.1')

        null = file('/dev/null', 'wb')
        a1 = n1.Popen(['ping', '-qc1', '10.0.1.2'], stdout = null)
        a2 = n3.Popen(['ping', '-qc1', '10.0.0.1'], stdout = null)
        self.assertEquals(a1.wait(), 0)
        self.assertEquals(a2.wait(), 0)

    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_run_ping_routing(self):
        n1 = nemu.Node()
        n2 = nemu.Node()
        n3 = nemu.Node()
        i1 = n1.add_if()
        i2a = n2.add_if()
        i2b = n2.add_if()
        i3 = n3.add_if()
        i1.up = i2a.up = i2b.up = i3.up = True
        l1 = nemu.Switch()
        l2 = nemu.Switch()
        l1.connect(i1)
        l1.connect(i2a)
        l2.connect(i2b)
        l2.connect(i3)
        l1.up = l2.up = True
        i1.add_v4_address('10.0.0.1', 24)
        i2a.add_v4_address('10.0.0.2', 24)
        i2b.add_v4_address('10.0.1.1', 24)
        i3.add_v4_address('10.0.1.2', 24)

        n1.add_route(prefix = '10.0.1.0', prefix_len = 24,
                nexthop = '10.0.0.2')
        n3.add_route(prefix = '10.0.0.0', prefix_len = 24,
                nexthop = '10.0.1.1')

        null = file('/dev/null', 'wb')
        a1 = n1.Popen(['ping', '-qc1', '10.0.1.2'], stdout = null)
        a2 = n3.Popen(['ping', '-qc1', '10.0.0.1'], stdout = null)
        self.assertEquals(a1.wait(), 0)
        self.assertEquals(a2.wait(), 0)

    def _forward_packets(self, subproc, if1, if2):
        while(True):
            ready = select.select([if1.fd, if2.fd], [], [], 0.1)[0]
            if ready:
                s = os.read(ready[0], 65536)
                if ready[0] == if1.fd:
                    os.write(if2.fd, s)
                else:
                    os.write(if1.fd, s)
                if not s:
                    break
            if subproc.poll() != None:
                break

    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_run_ping_tun(self):
        """This test simulates a point to point connection between two hosts
        using two tun devices."""
        n1 = nemu.Node()
        n2 = nemu.Node()

        # Use PI, so that's tested too.
        tun1 = n1.add_tun(use_pi = True)
        tun2 = n2.add_tun(use_pi = True)
        tun1.up = tun2.up = True

        tun1.add_v4_address('10.0.1.1', 24)
        tun2.add_v4_address('10.0.1.2', 24)

        null = file('/dev/null', 'wb')
        a = n1.Popen(['ping', '-qc1', '10.0.1.2'], stdout = null)
        self._forward_packets(a, tun1, tun2)
        self.assertEquals(a.wait(), 0)

    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_run_ping_tap(self):
        """This test simulates a point to point connection between two hosts
        using two tap devices."""
        n1 = nemu.Node()
        n2 = nemu.Node()

        tap1 = n1.add_tap()
        tap2 = n2.add_tap()
        tap1.up = tap2.up = True

        tap1.add_v4_address('10.0.1.1', 24)
        tap2.add_v4_address('10.0.1.2', 24)

        null = file('/dev/null', 'wb')
        a = n1.Popen(['ping', '-qc1', '10.0.1.2'], stdout = null)
        self._forward_packets(a, tap1, tap2)
        self.assertEquals(a.wait(), 0)

    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_run_ping_tap_routing(self):
        """This test simulates a point to point connection between two hosts
        using two tap devices, and normal connections with other two, to use
        routing."""
        n1 = nemu.Node()
        n2 = nemu.Node()
        n3 = nemu.Node()
        n4 = nemu.Node()

        i1 = n1.add_if()
        i2 = n2.add_if()
        tap1 = n2.add_tap()
        tap2 = n3.add_tap()
        i3 = n3.add_if()
        i4 = n4.add_if()

        i1.up = i2.up = tap1.up = tap2.up = i3.up = i4.up = True

        l1 = nemu.Switch()
        l2 = nemu.Switch()

        l1.connect(i1)
        l1.connect(i2)
        l2.connect(i3)
        l2.connect(i4)

        l1.up = l2.up = True

        i1.add_v4_address('10.0.0.1', 24)
        i2.add_v4_address('10.0.0.2', 24)
        tap1.add_v4_address('10.0.1.1', 24)
        tap2.add_v4_address('10.0.1.2', 24)
        i3.add_v4_address('10.0.2.1', 24)
        i4.add_v4_address('10.0.2.2', 24)

        n1.add_route(prefix = '10.0.1.0', prefix_len = 24, nexthop = '10.0.0.2')
        n1.add_route(prefix = '10.0.2.0', prefix_len = 24, nexthop = '10.0.0.2')
        n2.add_route(prefix = '10.0.2.0', prefix_len = 24, nexthop = '10.0.1.2')
        n3.add_route(prefix = '10.0.0.0', prefix_len = 24, nexthop = '10.0.1.1')
        n4.add_route(prefix = '10.0.1.0', prefix_len = 24, nexthop = '10.0.2.1')
        n4.add_route(prefix = '10.0.0.0', prefix_len = 24, nexthop = '10.0.2.1')

        null = file('/dev/null', 'wb')
        a = n1.Popen(['ping', '-qc1', '10.0.2.2'], stdout = null)
        self._forward_packets(a, tap1, tap2)
        self.assertEquals(a.wait(), 0)

class TestX11(unittest.TestCase):
    @test_util.skipUnless("DISPLAY" in os.environ, "Test requires working X11")
    @test_util.skipUnless(nemu.environ.XDPYINFO_PATH, "Test requires xdpyinfo")
    def test_run_xdpyinfo(self):
        xdpy = nemu.environ.XDPYINFO_PATH
        info = nemu.environ.backticks([xdpy])
        # remove first line, contains the display name
        info = info.partition("\n")[2]
        n = nemu.Node(nonetns = True, forward_X11 = True)
        info2 = n.backticks([xdpy])
        info2 = info2.partition("\n")[2]
        self.assertEquals(info, info2)

    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    @test_util.skipUnless("DISPLAY" in os.environ, "Test requires working X11")
    @test_util.skipUnless(nemu.environ.XDPYINFO_PATH, "Test requires xdpyinfo")
    def test_run_xdpyinfo_netns(self):
        xdpy = nemu.environ.XDPYINFO_PATH
        info = nemu.environ.backticks([xdpy])
        # remove first line, contains the display name
        info = info.partition("\n")[2]
        n = nemu.Node(forward_X11 = True)
        info2 = n.backticks([xdpy])
        info2 = info2.partition("\n")[2]
        self.assertEquals(info, info2)

if __name__ == '__main__':
    unittest.main()
