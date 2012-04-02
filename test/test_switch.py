#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import os, unittest
import nemu, test_util, nemu.environ

class TestSwitch(unittest.TestCase):
    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def setUp(self):
        n1 = nemu.Node()
        n2 = nemu.Node()
        i1 = n1.add_if()
        i2 = n2.add_if()
        l = nemu.Switch()
        l.connect(i1)
        l.connect(i2)
        self.stuff = (n1, n2, i1, i2, l)

    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_switch_base(self):
        (n1, n2, i1, i2, l) = self.stuff
        l.mtu = 3000
        ifdata = nemu.iproute.get_if_data()[0]
        self.assertEquals(ifdata[l.index].mtu, 3000)
        self.assertEquals(ifdata[i1.control.index].mtu, 3000,
                "MTU propagation")
        self.assertEquals(ifdata[i2.control.index].mtu, 3000,
                "MTU propagation")
        i1.mtu = i2.mtu = 3000

        self.assertEquals(ifdata[l.index].up, False)
        self.assertEquals(ifdata[i1.control.index].up, False,
                "UP propagation")
        self.assertEquals(ifdata[i2.control.index].up, False,
                "UP propagation")

        l.up = True
        ifdata = nemu.iproute.get_if_data()[0]
        self.assertEquals(ifdata[i1.control.index].up, True, "UP propagation")
        self.assertEquals(ifdata[i2.control.index].up, True, "UP propagation")

        tcdata = nemu.iproute.get_tc_data()[0]
        self.assertEquals(tcdata[i1.control.index], {"qdiscs": {}})
        self.assertEquals(tcdata[i2.control.index], {"qdiscs": {}})

    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_switch_changes(self):
        (n1, n2, i1, i2, l) = self.stuff

        # Test strange rules handling
        os.system(("%s qd add dev %s root prio bands 3 " +
            "priomap 1 2 2 2 1 2 0 0 1 1 1 1 1 1 1 1") %
            (nemu.environ.TC_PATH, i1.control.name))
        tcdata = nemu.iproute.get_tc_data()[0]
        self.assertEquals(tcdata[i1.control.index], "foreign")
        l.set_parameters(bandwidth = 13107200) # 100 mbits
        tcdata = nemu.iproute.get_tc_data()[0]
        self.assertEquals(tcdata[i1.control.index],
                {"bandwidth": 13107000, "qdiscs": {"tbf": "1"}})

        # Test tc replacements

        self._test_tbf()   # none  => tbf
        self._test_both()  # tbf   => both
        self._test_netem() # both  => netem
        self._test_tbf()   # netem => tbf
        self._test_netem() # tbf   => netem
        self._test_none()  # netem => none
        self._test_netem() # none  => netem
        self._test_both()  # netem => both
        self._test_tbf()   # both  => tbf
        self._test_none()  # tbf   => none
        self._test_both()  # none  => both
        self._test_none()  # both  => none

    def _test_none(self):
        (n1, n2, i1, i2, l) = self.stuff
        l.set_parameters()
        tcdata = nemu.iproute.get_tc_data()[0]
        self.assertEquals(tcdata[i1.control.index], {"qdiscs": {}})
        self.assertEquals(tcdata[i2.control.index], {"qdiscs": {}})

    def _test_tbf(self):
        (n1, n2, i1, i2, l) = self.stuff
        l.set_parameters(bandwidth = 13107200) # 100 mbits
        tcdata = nemu.iproute.get_tc_data()[0]
        self.assertEquals(tcdata[i1.control.index],
                # adjust for tc rounding
                {"bandwidth": 13107000, "qdiscs": {"tbf": "1"}})
        self.assertEquals(tcdata[i2.control.index],
                {"bandwidth": 13107000, "qdiscs": {"tbf": "1"}})

    def _test_netem(self):
        (n1, n2, i1, i2, l) = self.stuff
        l.set_parameters(delay = 0.001) # 1ms
        tcdata = nemu.iproute.get_tc_data()[0]
        self.assertEquals(tcdata[i1.control.index],
                {"delay": 0.001, "qdiscs": {"netem": "2"}})
        self.assertEquals(tcdata[i2.control.index],
                {"delay": 0.001, "qdiscs": {"netem": "2"}})

    def _test_both(self):
        (n1, n2, i1, i2, l) = self.stuff
        l.set_parameters(bandwidth = 13107200, delay = 0.001) # 100 mbits, 1ms
        tcdata = nemu.iproute.get_tc_data()[0]
        self.assertEquals(tcdata[i1.control.index],
                {"bandwidth": 13107000, "delay": 0.001,
                    "qdiscs": {"tbf": "1", "netem": "2"}})
        self.assertEquals(tcdata[i2.control.index],
                {"bandwidth": 13107000, "delay": 0.001,
                    "qdiscs": {"tbf": "1", "netem": "2"}})

if __name__ == "__main__":
    unittest.main()
