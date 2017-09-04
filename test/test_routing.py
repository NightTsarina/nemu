#!/usr/bin/env python2
# vim:ts=4:sw=4:et:ai:sts=4

import nemu, test_util
import os, unittest

class TestRouting(unittest.TestCase):
    @test_util.skip("Programatic detection of duplicate routes not implemented")
    def test_base_routing(self):
        node = nemu.Node(nonetns = True)
        routes = node.get_routes() # main netns routes!
        if(len(routes)):
            self.assertRaises(RuntimeError, node.add_route, routes[0])
            routes[0].metric += 1 # should be enough to make it unique
            self.assertRaises(RuntimeError, node.del_route, routes[0])

    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_routing(self):
        node = nemu.Node()
        self.assertEquals(len(node.get_routes()), 0)

        if0 = node.add_if()
        if0.add_v4_address('10.0.0.1', 24)
        if0.up = True
        routes = node.get_routes()
        self.assertEquals(routes, [node.route(prefix = '10.0.0.0',
            prefix_len = 24, interface = if0)])

        node.add_route(nexthop = '10.0.0.2') # default route
        node.add_route(prefix = '10.1.0.0', prefix_len = 16,
                nexthop = '10.0.0.3')
        node.add_route(prefix = '11.1.0.1', prefix_len = 32, interface = if0)

        routes = node.get_routes()
        self.assertTrue(node.route(nexthop = '10.0.0.2', interface = if0)
                in routes)
        self.assertTrue(node.route(prefix = '10.1.0.0', prefix_len = 16,
            nexthop = '10.0.0.3', interface = if0) in routes)
        self.assertTrue(node.route(prefix = '11.1.0.1', prefix_len = 32,
            interface = if0) in routes)

        node.del_route(nexthop = '10.0.0.2') # default route
        node.del_route(prefix = '10.1.0.0', prefix_len = 16,
                nexthop = '10.0.0.3')
        node.del_route(prefix = '11.1.0.1', prefix_len = 32, interface = if0)
        node.del_route(prefix = '10.0.0.0', prefix_len = 24, interface = if0)

        self.assertEquals(node.get_routes(), [])

if __name__ == '__main__':
    unittest.main()

