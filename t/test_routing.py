#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import netns, test_util
import os, unittest

class TestRouting(unittest.TestCase):
    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_routing(self):
        node = netns.Node()
        if0 = node.add_if()
        if0.add_v4_address('10.0.0.1', 24)
        node.add_default_route(nexthop = '10.0.0.2')
        node.add_route(prefix = '10.1.0.0', prefix_len = 16,
                nexthop = '10.0.0.3')
        node.add_route(prefix = '11.1.0.1', prefix_len = 32, interface = if0)

        routes = node.get_routes()
        # FIXME:...

if __name__ == '__main__':
    unittest.main()

