#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import unittest
import netns

class TestConfigure(unittest.TestCase):
    def setUp(self):
        # Default == nobody || (uid_t) -1
        import pwd
        try:
            self.nobodyid = pwd.getpwnam('nobody')[2]
        except:
            self.nobodyid = None
    def test_config_run_as_static(self):
        # Not allow root as default user
        self.assertRaises(AttributeError, setattr, netns.config,
                'run_as', 'root')
        self.assertRaises(AttributeError, setattr, netns.config,
                'run_as', 0)
        self.assertEquals(netns.config.run_as, self.nobodyid or 65535)

    def test_config_run_as_runtime(self):
        netns.config.run_as = (self.nobodyid or 65535)
        node = netns.Node()
        app = node.start_process(["sleep", "1000"])
        pid = app.pid
        # FIXME: non-portable *at all*
        stat = open("/proc/%d/status" % pid)
        while True:
            data = stat.readline()
            fields = data.split()
            if fields[0] != 'Uid:':
                continue
            uid = fields[1]
            break
        stat.close()
        self.assertEquals(uid, (self.nobodyid or 65535))

if __name__ == '__main__':
    unittest.main()
