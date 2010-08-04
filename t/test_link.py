#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import os, unittest
import netns, test_util

class TestLink(unittest.TestCase):
    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_link(self):
        n1 = netns.Node()
        n2 = netns.Node()
        i1 = n1.add_if()
        i2 = n2.add_if()
        l = netns.Link()
        l.connect(i1)
        l.connect(i2)

        l.mtu = 3000
        ifdata = netns.iproute.get_if_data()[0]
        self.assertEquals(ifdata[l.index].mtu, 3000)
        self.assertEquals(ifdata[i1.control.index].mtu, 3000, "MTU propagation")
        self.assertEquals(ifdata[i2.control.index].mtu, 3000, "MTU propagation")
        i1.mtu = i2.mtu = 3000

        self.assertEquals(ifdata[l.index].up, False)
        self.assertEquals(ifdata[i1.control.index].up, False, "UP propagation")
        self.assertEquals(ifdata[i2.control.index].up, False, "UP propagation")

        l.up = True
        ifdata = netns.iproute.get_if_data()[0]
        self.assertEquals(ifdata[i1.control.index].up, True, "UP propagation")
        self.assertEquals(ifdata[i2.control.index].up, True, "UP propagation")

        # None => tbf
        l.set_parameters(bandwidth = 100*1024*1024/8) # 100 mbits
        tcdata = netns.iproute.get_tc_data()[0]
        self.assertEquals(tcdata[i1.control.index],
                {'bandwidth': 104858000, 'qdiscs': {'tbf': '1'}})
        self.assertEquals(tcdata[i2.control.index],
                {'bandwidth': 104858000, 'qdiscs': {'tbf': '1'}})
        #bandwidth = 100*1024*1024/8, loss=10, loss_correlation=1,delay=0.001,dup_correlation=0.1); 
        # FIXME: more cases

if __name__ == '__main__':
    unittest.main()
