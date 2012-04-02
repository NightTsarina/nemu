#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import nemu, test_util
import nemu.subprocess_ as sp
import grp, os, pwd, signal, socket, sys, time, unittest

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
        pid = sp.spawn('/bin/sleep', ['/bin/sleep', '100'], user = user)
        self._check_ownership(user, pid)
        os.kill(pid, signal.SIGTERM)
        self.assertEquals(sp.wait(pid), signal.SIGTERM)

    @test_util.skipUnless(os.getuid() == 0, "Test requires root privileges")
    def test_Subprocess_chuser(self):
        node = nemu.Node(nonetns = True)
        user = 'nobody'
        p = node.Subprocess(['/bin/sleep', '1000'], user = user)
        self._check_ownership(user, p.pid)
        p.signal()
        self.assertEquals(p.wait(), -signal.SIGTERM)

    def test_spawn_basic(self):
        # User does not exist
        self.assertRaises(ValueError, sp.spawn,
                '/bin/sleep', ['/bin/sleep', '1000'], user = self.nouser)
        self.assertRaises(ValueError, sp.spawn,
                '/bin/sleep', ['/bin/sleep', '1000'], user = self.nouid)
        # Invalid CWD: it is a file
        self.assertRaises(OSError, sp.spawn, '/bin/sleep', cwd = '/bin/sleep')
        # Invalid CWD: does not exist
        self.assertRaises(OSError, sp.spawn, '/bin/sleep', cwd = self.nofile)
        # Exec failure
        self.assertRaises(OSError, sp.spawn, self.nofile)

        # Test that the environment is cleared: sleep should not be found
        # XXX: This should be a python bug: if I don't set PATH explicitly, it
        # uses a default search path
        self.assertRaises(OSError, sp.spawn, 'sleep', env = {'PATH': ''})

        r, w = os.pipe()
        p = sp.spawn('/bin/echo', ['echo', 'hello world'], stdout = w)
        os.close(w)
        self.assertEquals(_readall(r), "hello world\n")
        os.close(r)

        # Check poll.
        while True:
            ret = sp.poll(p)
            if ret is not None:
                self.assertEquals(ret, 0)
                break
            time.sleep(0.2)  # Wait a little bit.
        # It cannot be wait()ed again.
        self.assertRaises(OSError, sp.wait, p)

        r0, w0 = os.pipe()
        r1, w1 = os.pipe()
        p = sp.spawn('/bin/cat', stdout = w0, stdin = r1, close_fds = [r0, w1])
        os.close(w0)
        os.close(r1)
        self.assertEquals(sp.poll(p), None)
        os.write(w1, "hello world\n")
        os.close(w1)
        self.assertEquals(_readall(r0), "hello world\n")
        os.close(r0)
        self.assertEquals(sp.wait(p), 0)

    def test_Subprocess_basic(self):
        node = nemu.Node(nonetns = True)
        # User does not exist
        self.assertRaises(ValueError, node.Subprocess,
                ['/bin/sleep', '1000'], user = self.nouser)
        self.assertRaises(ValueError, node.Subprocess,
                ['/bin/sleep', '1000'], user = self.nouid)
        # Invalid CWD: it is a file
        self.assertRaises(OSError, node.Subprocess,
                '/bin/sleep', cwd = '/bin/sleep')
        # Invalid CWD: does not exist
        self.assertRaises(OSError, node.Subprocess,
                '/bin/sleep', cwd = self.nofile)
        # Exec failure
        self.assertRaises(OSError, node.Subprocess, self.nofile)
        # Test that the environment is cleared: sleep should not be found
        self.assertRaises(OSError, node.Subprocess,
                'sleep', env = {'PATH': ''})

        # Argv
        self.assertRaises(OSError, node.Subprocess, 'true; false')
        self.assertEquals(node.Subprocess('true').wait(), 0)
        self.assertEquals(node.Subprocess('true; false', shell = True).wait(),
                1)

        # Piping
        r, w = os.pipe()
        p = node.Subprocess(['echo', 'hello world'], stdout = w)
        os.close(w)
        self.assertEquals(_readall(r), "hello world\n")
        os.close(r)
        p.wait()

        # cwd
        r, w = os.pipe()
        p = node.Subprocess('/bin/pwd', stdout = w, cwd = "/")
        os.close(w)
        self.assertEquals(_readall(r), "/\n")
        os.close(r)
        p.wait()

        p = node.Subprocess(['sleep', '100'])
        self.assertTrue(p.pid > 0)
        self.assertEquals(p.poll(), None) # not finished
        p.signal()
        p.signal() # verify no-op (otherwise there will be an exception)
        self.assertEquals(p.wait(), -signal.SIGTERM)
        self.assertEquals(p.wait(), -signal.SIGTERM) # no-op
        self.assertEquals(p.poll(), -signal.SIGTERM) # no-op

        # destroy
        p = node.Subprocess(['sleep', '100'])
        pid = p.pid
        os.kill(pid, 0) # verify process still there
        p.destroy()
        self.assertRaises(OSError, os.kill, pid, 0) # should be dead by now

        # forceful destroy
        # Command: ignore SIGTERM, write \n to synchronise and then sleep while
        # closing stdout (so _readall finishes)
        cmd = 'trap "" TERM; echo; exec sleep 100 > /dev/null'

        r, w = os.pipe()
        p = node.Subprocess(cmd, shell = True, stdout = w)
        os.close(w)
        self.assertEquals(_readall(r), "\n") # wait for trap to be installed
        os.close(r)
        pid = p.pid
        os.kill(pid, 0) # verify process still there
        # Avoid the warning about the process being killed
        orig_stderr = sys.stderr
        sys.stderr = open("/dev/null", "w")
        p.destroy()
        sys.stderr = orig_stderr
        self.assertRaises(OSError, os.kill, pid, 0) # should be dead by now

        p = node.Subprocess(['sleep', '100'])
        os.kill(p.pid, signal.SIGTERM)
        time.sleep(0.2)
        p.signal() # since it has not been waited for, it should not raise
        self.assertEquals(p.wait(), -signal.SIGTERM)

    def test_Popen(self):
        node = nemu.Node(nonetns = True)

        # repeat test with Popen interface
        r0, w0 = os.pipe()
        r1, w1 = os.pipe()
        p = node.Popen('cat', stdout = w0, stdin = r1)
        os.close(w0)
        os.close(r1)
        os.write(w1, "hello world\n")
        os.close(w1)
        self.assertEquals(_readall(r0), "hello world\n")
        os.close(r0)

        # now with a socketpair, not using integers
        (s0, s1) = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM, 0)
        p = node.Popen('cat', stdout = s0, stdin = s0)
        s0.close()
        s1.send("hello world\n")
        self.assertEquals(s1.recv(512), "hello world\n")
        s1.close()

        # pipes
        p = node.Popen('cat', stdin = sp.PIPE, stdout = sp.PIPE)
        p.stdin.write("hello world\n")
        p.stdin.close()
        self.assertEquals(p.stdout.readlines(), ["hello world\n"])
        self.assertEquals(p.stderr, None)
        self.assertEquals(p.wait(), 0)

        p = node.Popen('cat', stdin = sp.PIPE, stdout = sp.PIPE)
        self.assertEquals(p.communicate(_longstring), (_longstring, None))

        p = node.Popen('cat', stdin = sp.PIPE, stdout = sp.PIPE)
        p.stdin.write(_longstring)
        self.assertEquals(p.communicate(), (_longstring, None))

        p = node.Popen('cat', stdin = sp.PIPE)
        self.assertEquals(p.communicate(), (None, None))

        p = node.Popen('cat >&2', shell = True, stdin = sp.PIPE,
                stderr = sp.PIPE)
        p.stdin.write("hello world\n")
        p.stdin.close()
        self.assertEquals(p.stderr.readlines(), ["hello world\n"])
        self.assertEquals(p.stdout, None)
        self.assertEquals(p.wait(), 0)

        p = node.Popen(['sh', '-c', 'cat >&2'], stdin = sp.PIPE,
                stderr = sp.PIPE)
        self.assertEquals(p.communicate(_longstring), (None, _longstring))

        #
        p = node.Popen(['sh', '-c', 'cat >&2'],
                stdin = sp.PIPE, stdout = sp.PIPE, stderr = sp.STDOUT)
        p.stdin.write("hello world\n")
        p.stdin.close()
        self.assertEquals(p.stdout.readlines(), ["hello world\n"])
        self.assertEquals(p.stderr, None)
        self.assertEquals(p.wait(), 0)

        p = node.Popen(['sh', '-c', 'cat >&2'],
                stdin = sp.PIPE, stdout = sp.PIPE, stderr = sp.STDOUT)
        self.assertEquals(p.communicate(_longstring), (_longstring, None))

        #
        p = node.Popen(['tee', '/dev/stderr'],
                stdin = sp.PIPE, stdout = sp.PIPE, stderr = sp.STDOUT)
        p.stdin.write("hello world\n")
        p.stdin.close()
        self.assertEquals(p.stdout.readlines(), ["hello world\n"] * 2)
        self.assertEquals(p.stderr, None)
        self.assertEquals(p.wait(), 0)

        p = node.Popen(['tee', '/dev/stderr'],
                stdin = sp.PIPE, stdout = sp.PIPE, stderr = sp.STDOUT)
        self.assertEquals(p.communicate(_longstring[0:512]),
                (_longstring[0:512] * 2, None))

        #
        p = node.Popen(['tee', '/dev/stderr'],
                stdin = sp.PIPE, stdout = sp.PIPE, stderr = sp.PIPE)
        p.stdin.write("hello world\n")
        p.stdin.close()
        self.assertEquals(p.stdout.readlines(), ["hello world\n"])
        self.assertEquals(p.stderr.readlines(), ["hello world\n"])
        self.assertEquals(p.wait(), 0)

        p = node.Popen(['tee', '/dev/stderr'],
                stdin = sp.PIPE, stdout = sp.PIPE, stderr = sp.PIPE)
        self.assertEquals(p.communicate(_longstring), (_longstring, ) * 2)

    def test_backticks(self):
        node = nemu.Node(nonetns = True)
        self.assertEquals(node.backticks("echo hello world"), "hello world\n")
        self.assertEquals(node.backticks(r"echo hello\ \ world"),
                "hello  world\n")
        self.assertEquals(node.backticks(["echo", "hello", "world"]),
                "hello world\n")
        self.assertEquals(node.backticks("echo hello world > /dev/null"), "")
        self.assertEquals(node.backticks_raise("true"), "")
        self.assertRaises(RuntimeError, node.backticks_raise, "false")
        self.assertRaises(RuntimeError, node.backticks_raise, "kill $$")

    def test_system(self):
        node = nemu.Node(nonetns = True)
        self.assertEquals(node.system("true"), 0)
        self.assertEquals(node.system("false"), 1)

if __name__ == '__main__':
    unittest.main()

