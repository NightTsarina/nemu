#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import netns, netns.environ, test_util
import os, signal, subprocess, sys, time
import unittest

class TestNode(unittest.TestCase):
    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_node(self):
        node = netns.Node()
        self.failIfEqual(node.pid, os.getpid())
        self.failIfEqual(node.pid, None)
        # check if it really exists
        os.kill(node.pid, 0)

        nodes = netns.get_nodes()
        self.assertEquals(nodes, [node])

    @test_util.skip("Not implemented")
    def test_detect_fork(self):
        # Test that netns recognises a fork
        chld = os.fork()
        if chld == 0:
            if len(netns.get_nodes()) == 0:
                os._exit(0)
            os._exit(1)
        (pid, exitcode) = os.waitpid(chld, 0)
        self.assertEquals(exitcode, 0, "Node does not recognise forks")

    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_cleanup(self):
        def create_stuff():
            a = netns.Node()
            b = netns.Node()
            ifa = a.add_if()
            ifb = b.add_if()
            link = netns.Link()
            link.connect(ifa)
            link.connect(ifb)

        # Test automatic destruction
        orig_devs = len(test_util.get_devs())
        create_stuff()
        self.assertEquals(netns.get_nodes(), [])
        self.assertEquals(orig_devs, len(test_util.get_devs()))

        # Test at_exit hooks
        orig_devs = len(test_util.get_devs())
        chld = os.fork()
        if chld == 0:
            netns.set_cleanup_hooks(on_exit = True, on_signals = [])
            create_stuff()
            os._exit(0)
        os.waitpid(chld, 0)
        self.assertEquals(orig_devs, len(test_util.get_devs()))

        # Test signal hooks
        orig_devs = len(test_util.get_devs())
        chld = os.fork()
        if chld == 0:
            netns.set_cleanup_hooks(on_exit = False,
                    on_signals = [signal.SIGTERM])
            create_stuff()
            while True:
                time.sleep(10)
        os.kill(chld, signal.SIGTERM)
        os.waitpid(chld, 0)
        self.assertEquals(orig_devs, len(test_util.get_devs()))

if __name__ == '__main__':
    unittest.main()

