#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import grp, pwd, unittest
import netns

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

    def test_config_run_as_runtime(self):
        user = netns.config.run_as = 'nobody'
        uid = pwd.getpwnam(user)[2]
        gid = pwd.getpwnam(user)[3]
        groups = [x[2] for x in grp.getgrall() if user in x[3]]

        node = netns.Node()
        app = node.start_process(["sleep", "1000"])
        pid = app.pid
        # FIXME: non-portable *at all*
        stat = open("/proc/%d/status" % pid)
        while True:
            data = stat.readline()
            fields = data.split()
            if fields[0] == 'Uid:':
                self.assertEquals(fields[1:4], (uid,) * 4)
            if fields[0] == 'Gid:':
                self.assertEquals(fields[1:4], (gid,) * 4)
            if fields[0] == 'Groups:':
                self.assertEquals(set(fields[1:]), set(groups))
            break
        stat.close()

if __name__ == '__main__':
    unittest.main()
