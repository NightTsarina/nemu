#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import netns, netns.subprocess, test_util
import grp, os, pwd, signal, sys, unittest

def _stat(path):
    try:
        return os.stat(user)
    except:
        return None

def _getpwnam(user):
    try:
        return pwd.getpwnam(user)
    except:
        return None

def _getpwuid(uid):
    try:
        return pwd.getpwuid(uid)
    except:
        return None

def _readall(fd):
    s = ""
    while True:
        try:
            s1 = os.read(fd, 4096)
        except OSError, e:
            if e.errno == errno.EINTR:
                continue
            else:
                raise
        if s1 == "":
            break
        s += s1
    return s

class TestSubprocess(unittest.TestCase):
    def _check_ownership(self, user, pid):
        uid = pwd.getpwnam(user)[2]
        gid = pwd.getpwnam(user)[3]
        groups = [x[2] for x in grp.getgrall() if user in x[3]]
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

    def setUp(self):
        self.nouid = 65535
        while _getpwuid(self.nouid):
            self.nouid -= 1
        self.nouser = 'foobar'
        while _getpwnam(self.nouser):
            self.nouser += '_'
        self.nofile = '/foobar'
        while _stat(self.nofile):
            self.nofile += '_'

    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_spawn_chuser(self):
        user = 'nobody'
        pid = netns.subprocess.spawn('/bin/sleep', ['/bin/sleep', '100'],
                user = user)
        self._check_ownership(user, pid)
        os.kill(pid, signal.SIGTERM)
        self.assertEquals(netns.subprocess.wait(pid), signal.SIGTERM)

    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_Subprocess_chuser(self):
        node = netns.Node(nonetns = True)
        user = 'nobody'
        p = netns.subprocess.Subprocess(node, '/bin/sleep',
                ['/bin/sleep', '1000'], user = user)
        self._check_ownership(user, p.pid)
        p.signal()
        self.assertEquals(p.wait(), -signal.SIGTERM)

    def test_spawn_basic(self):
        # User does not exist
        self.assertRaises(ValueError, netns.subprocess.spawn,
                '/bin/sleep', ['/bin/sleep', '1000'], user = self.nouser)
        self.assertRaises(ValueError, netns.subprocess.spawn,
                '/bin/sleep', ['/bin/sleep', '1000'], user = self.nouid)
        # Invalid CWD: it is a file
        self.assertRaises(OSError, netns.subprocess.spawn,
                '/bin/sleep', cwd = '/bin/sleep')
        # Invalid CWD: does not exist
        self.assertRaises(OSError, netns.subprocess.spawn,
                '/bin/sleep', cwd = self.nofile)
        # Exec failure
        self.assertRaises(OSError, netns.subprocess.spawn, self.nofile)

        # Test that the environment is cleared: sleep should not be found
        # XXX: This should be a python bug: if I don't set PATH explicitly, it
        # uses a default search path
        self.assertRaises(OSError, netns.subprocess.spawn,
                'sleep', env = {'PATH': ''})

        r, w = os.pipe()
        p = netns.subprocess.spawn('/bin/echo', ['echo', 'hello world'],
                stdout = w)
        os.close(w)
        self.assertEquals(_readall(r), "hello world\n")
        os.close(r)

    def test_Subprocess_basic(self):
        node = netns.Node(nonetns = True) #, debug = True)
        # User does not exist
        self.assertRaises(RuntimeError, netns.subprocess.Subprocess, node,
                '/bin/sleep', ['/bin/sleep', '1000'], user = self.nouser)
        self.assertRaises(RuntimeError, netns.subprocess.Subprocess, node,
                '/bin/sleep', ['/bin/sleep', '1000'], user = self.nouid)
        # Invalid CWD: it is a file
        self.assertRaises(RuntimeError, netns.subprocess.Subprocess, node,
                '/bin/sleep', cwd = '/bin/sleep')
        # Invalid CWD: does not exist
        self.assertRaises(RuntimeError, netns.subprocess.Subprocess, node,
                '/bin/sleep', cwd = self.nofile)
        # Exec failure
        self.assertRaises(RuntimeError, netns.subprocess.Subprocess, node,
                self.nofile)
        # Test that the environment is cleared: sleep should not be found
        # XXX: This should be a python bug: if I don't set PATH explicitly, it
        # uses a default search path
        self.assertRaises(RuntimeError, netns.subprocess.Subprocess, node,
                'sleep', env = {'PATH': ''})
        # FIXME: tests fds
        r, w = os.pipe()
        p = netns.subprocess.Subprocess(node, '/bin/echo',
                ['echo', 'hello world'], stdout = w)
        os.close(w)
        self.assertEquals(_readall(r), "hello world\n")
        os.close(r)

# FIXME: tests for Popen!
if __name__ == '__main__':
    unittest.main()

