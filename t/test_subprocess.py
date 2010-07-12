#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import netns, netns.subprocess_, test_util
import grp, os, pwd, signal, socket, sys, time, unittest

from netns.subprocess_ import *

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
_longstring = "Long string is long!\n" * 1000

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
        pid = spawn('/bin/sleep', ['/bin/sleep', '100'], user = user)
        self._check_ownership(user, pid)
        os.kill(pid, signal.SIGTERM)
        self.assertEquals(wait(pid), signal.SIGTERM)

    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_Subprocess_chuser(self):
        node = netns.Node(nonetns = True)
        user = 'nobody'
        p = Subprocess(node, ['/bin/sleep', '1000'], user = user)
        self._check_ownership(user, p.pid)
        p.signal()
        self.assertEquals(p.wait(), -signal.SIGTERM)

    def test_spawn_basic(self):
        # User does not exist
        self.assertRaises(ValueError, spawn,
                '/bin/sleep', ['/bin/sleep', '1000'], user = self.nouser)
        self.assertRaises(ValueError, spawn,
                '/bin/sleep', ['/bin/sleep', '1000'], user = self.nouid)
        # Invalid CWD: it is a file
        self.assertRaises(OSError, spawn, '/bin/sleep', cwd = '/bin/sleep')
        # Invalid CWD: does not exist
        self.assertRaises(OSError, spawn, '/bin/sleep', cwd = self.nofile)
        # Exec failure
        self.assertRaises(OSError, spawn, self.nofile)

        # Test that the environment is cleared: sleep should not be found
        # XXX: This should be a python bug: if I don't set PATH explicitly, it
        # uses a default search path
        self.assertRaises(OSError, spawn, 'sleep', env = {'PATH': ''})

        r, w = os.pipe()
        p = spawn('/bin/echo', ['echo', 'hello world'], stdout = w)
        os.close(w)
        self.assertEquals(_readall(r), "hello world\n")
        os.close(r)

        r0, w0 = os.pipe()
        r1, w1 = os.pipe()
        p = spawn('/bin/cat', stdout = w0, stdin = r1, close_fds = [r0, w1])
        os.close(w0)
        os.close(r1)
        self.assertEquals(poll(p), None)
        os.write(w1, "hello world\n")
        os.close(w1)
        self.assertEquals(_readall(r0), "hello world\n")
        os.close(r0)
        self.assertEquals(wait(p), 0)

    def test_Subprocess_basic(self):
        node = netns.Node(nonetns = True, debug = 0)
        # User does not exist
        self.assertRaises(ValueError, Subprocess, node,
                ['/bin/sleep', '1000'], user = self.nouser)
        self.assertRaises(ValueError, Subprocess, node,
                ['/bin/sleep', '1000'], user = self.nouid)
        # Invalid CWD: it is a file
        self.assertRaises(OSError, Subprocess, node,
                '/bin/sleep', cwd = '/bin/sleep')
        # Invalid CWD: does not exist
        self.assertRaises(OSError, Subprocess, node,
                '/bin/sleep', cwd = self.nofile)
        # Exec failure
        self.assertRaises(OSError, Subprocess, node, self.nofile)
        # Test that the environment is cleared: sleep should not be found
        self.assertRaises(OSError, Subprocess, node,
                'sleep', env = {'PATH': ''})

        # Argv
        self.assertRaises(OSError, Subprocess, node, 'true; false')
        self.assertEquals(Subprocess(node, 'true').wait(), 0)
        self.assertEquals(Subprocess(node, 'true; false', shell = True).wait(),
                1)

        # Piping
        r, w = os.pipe()
        p = Subprocess(node, ['echo', 'hello world'], stdout = w)
        os.close(w)
        self.assertEquals(_readall(r), "hello world\n")
        os.close(r)
        p.wait()

        p = Subprocess(node, ['sleep', '100'])
        self.assertTrue(p.pid > 0)
        self.assertEquals(p.poll(), None) # not finished
        p.signal()
        p.signal() # verify no-op (otherwise there will be an exception)
        self.assertEquals(p.wait(), -signal.SIGTERM)
        self.assertEquals(p.wait(), -signal.SIGTERM) # no-op
        self.assertEquals(p.poll(), -signal.SIGTERM) # no-op

        p = Subprocess(node, ['sleep', '100'])
        os.kill(p.pid, signal.SIGTERM)
        time.sleep(0.2)
        p.signal() # since it has not been waited for, it should not raise
        self.assertEquals(p.wait(), -signal.SIGTERM)

    def test_Popen(self):
        node = netns.Node(nonetns = True, debug = 0)

        # repeat test with Popen interface
        r0, w0 = os.pipe()
        r1, w1 = os.pipe()
        p = Popen(node, 'cat', stdout = w0, stdin = r1)
        os.close(w0)
        os.close(r1)
        os.write(w1, "hello world\n")
        os.close(w1)
        self.assertEquals(_readall(r0), "hello world\n")
        os.close(r0)

        # now with a socketpair, not using integers
        (s0, s1) = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM, 0)
        p = Popen(node, 'cat', stdout = s0, stdin = s0)
        s0.close()
        s1.send("hello world\n")
        self.assertEquals(s1.recv(512), "hello world\n")
        s1.close()

        # pipes
        p = Popen(node, 'cat', stdin = PIPE, stdout = PIPE)
        p.stdin.write("hello world\n")
        p.stdin.close()
        self.assertEquals(p.stdout.readlines(), ["hello world\n"])
        self.assertEquals(p.stderr, None)
        self.assertEquals(p.wait(), 0)

        p = Popen(node, 'cat', stdin = PIPE, stdout = PIPE)
        self.assertEquals(p.communicate(_longstring), (_longstring, None))

        p = Popen(node, 'cat', stdin = PIPE, stdout = PIPE)
        p.stdin.write(_longstring)
        self.assertEquals(p.communicate(), (_longstring, None))

        p = Popen(node, 'cat', stdin = PIPE)
        self.assertEquals(p.communicate(), (None, None))

        p = Popen(node, 'cat >&2', shell = True, stdin = PIPE, stderr = PIPE)
        p.stdin.write("hello world\n")
        p.stdin.close()
        self.assertEquals(p.stderr.readlines(), ["hello world\n"])
        self.assertEquals(p.stdout, None)
        self.assertEquals(p.wait(), 0)

        p = Popen(node, ['sh', '-c', 'cat >&2'], stdin = PIPE, stderr = PIPE)
        self.assertEquals(p.communicate(_longstring), (None, _longstring))

        #
        p = Popen(node, ['sh', '-c', 'cat >&2'],
                stdin = PIPE, stdout = PIPE, stderr = STDOUT)
        p.stdin.write("hello world\n")
        p.stdin.close()
        self.assertEquals(p.stdout.readlines(), ["hello world\n"])
        self.assertEquals(p.stderr, None)
        self.assertEquals(p.wait(), 0)

        p = Popen(node, ['sh', '-c', 'cat >&2'],
                stdin = PIPE, stdout = PIPE, stderr = STDOUT)
        self.assertEquals(p.communicate(_longstring), (_longstring, None))

        #
        p = Popen(node, ['tee', '/dev/stderr'],
                stdin = PIPE, stdout = PIPE, stderr = STDOUT)
        p.stdin.write("hello world\n")
        p.stdin.close()
        self.assertEquals(p.stdout.readlines(), ["hello world\n"] * 2)
        self.assertEquals(p.stderr, None)
        self.assertEquals(p.wait(), 0)

        p = Popen(node, ['tee', '/dev/stderr'],
                stdin = PIPE, stdout = PIPE, stderr = STDOUT)
        self.assertEquals(p.communicate(_longstring[0:512]),
                (_longstring[0:512] * 2, None))

        #
        p = Popen(node, ['tee', '/dev/stderr'],
                stdin = PIPE, stdout = PIPE, stderr = PIPE)
        p.stdin.write("hello world\n")
        p.stdin.close()
        self.assertEquals(p.stdout.readlines(), ["hello world\n"])
        self.assertEquals(p.stderr.readlines(), ["hello world\n"])
        self.assertEquals(p.wait(), 0)

        p = Popen(node, ['tee', '/dev/stderr'],
                stdin = PIPE, stdout = PIPE, stderr = PIPE)
        self.assertEquals(p.communicate(_longstring), (_longstring, ) * 2)

    def test_backticks(self): 
        node = netns.Node(nonetns = True, debug = 0)
        self.assertEquals(backticks(node, "echo hello world"), "hello world\n")
        self.assertEquals(backticks(node, r"echo hello\ \ world"),
                "hello  world\n")
        self.assertEquals(backticks(node, ["echo", "hello", "world"]),
                "hello world\n")
        self.assertEquals(backticks(node, "echo hello world > /dev/null"), "")
        self.assertEquals(backticks_raise(node, "true"), "")
        self.assertRaises(RuntimeError, backticks_raise, node, "false")
        self.assertRaises(RuntimeError, backticks_raise, node, "kill $$")

    def test_system(self): 
        node = netns.Node(nonetns = True, debug = 0)
        self.assertEquals(system(node, "true"), 0)
        self.assertEquals(system(node, "false"), 1)

# FIXME: tests for Popen!
if __name__ == '__main__':
    unittest.main()

