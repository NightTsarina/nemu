#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import netns.protocol
import os, socket, sys, unittest

class TestServer(unittest.TestCase):
    def test_server_startup(self):
        # Test the creation of the server object with different ways of passing
        # the file descriptor; and check the banner.
        (s0, s1) = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM, 0)
        (s2, s3) = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM, 0)
        pid = os.fork()
        if not pid:
            s1.close()
            srv = netns.protocol.Server(s0)
            srv.run()

            s3.close()
            srv = netns.protocol.Server(s2.fileno())
            srv.run()

            os._exit(0)

        s0.close()
        s = os.fdopen(s1.fileno(), "r+", 1)
        self.assertEquals(s.readline()[0:4], "220 ")
        s.close()

        s2.close()
        s = os.fdopen(s3.fileno(), "r+", 1)
        self.assertEquals(s.readline()[0:4], "220 ")
        s.close()
        pid, ret = os.waitpid(pid, 0)
        self.assertEquals(ret, 0)

    def test_spawn_recovery(self):
        (s0, s1) = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM, 0)
        pid = os.fork()
        if not pid:
            s1.close()
            srv = netns.protocol.Server(s0)
            srv.run()
            os._exit(0)
        cli = netns.protocol.Client(s1)
        s0.close()

        # make PROC SIN fail
        self.assertRaises(OSError, cli.spawn, "/bin/true", stdin = -1)
        # check if the protocol is in a sane state:
        # PROC CWD should not be valid
        cli._send_cmd("PROC", "CWD", "/")
        self.assertRaises(RuntimeError, cli._read_and_check_reply)
        cli.shutdown()
        pid, ret = os.waitpid(pid, 0)
        self.assertEquals(ret, 0)

    def test_basic_stuff(self):
        (s0, s1) = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM, 0)
        srv = netns.protocol.Server(s0)
        s1 = s1.makefile("r+", 1)

        def check_error(self, cmd, code = 500):
            s1.write("%s\n" % cmd)
            self.assertEquals(srv.readcmd(), None)
            self.assertEquals(s1.readline()[0:4], "%d " % code)
        def check_ok(self, cmd, func, args):
            s1.write("%s\n" % cmd)
            ccmd = " ".join(cmd.upper().split()[0:2])
            if func == None:
                self.assertEquals(srv.readcmd()[1:3], (ccmd, args))
            else:
                self.assertEquals(srv.readcmd(), (func, ccmd, args))

        check_ok(self, "quit", srv.do_QUIT, [])
        check_ok(self, " quit ", srv.do_QUIT, [])
        # protocol error
        check_error(self, "quit 1")

        # Not allowed in normal mode
        check_error(self, "proc user")
        check_error(self, "proc sin")
        check_error(self, "proc sout")
        check_error(self, "proc serr")
        check_error(self, "proc cwd")
        check_error(self, "proc env")
        check_error(self, "proc abrt")
        check_error(self, "proc run")

        # not implemented
        #check_ok(self, "if list", srv.do_IF_LIST, [])
        #check_ok(self, "if list 1", srv.do_IF_LIST, [1])
        check_error(self, "if list")

        check_error(self, "proc poll") # missing arg
        check_error(self, "proc poll 1 2") # too many args
        check_error(self, "proc poll a") # invalid type

        check_ok(self, "proc crte /bin/sh", srv.do_PROC_CRTE,
                ['/bin/sh'])
        # Commands that would fail, but the parsing is correct
        check_ok(self, "proc poll 0", None, [0])
        check_ok(self, "proc wait 0", None, [0])
        check_ok(self, "proc kill 0", None, [0])

        check_ok(self, "proc crte =", srv.do_PROC_CRTE, [""]) # empty b64
        check_error(self, "proc crte =a") # invalid b64

        # simulate proc mode
        srv.commands = netns.protocol._proc_commands
        check_error(self, "proc crte foo")
        check_error(self, "proc poll 0")
        check_error(self, "proc wait 0")
        check_error(self, "proc kill 0")

if __name__ == '__main__':
    unittest.main()
