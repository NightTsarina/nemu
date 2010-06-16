#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

# FIXME:
# Not only missing docs; this would be nicer if merged the spawn_slave
# functionality also. need to investigate...


try:
    from yaml import CLoader as Loader
    from yaml import CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

import base64, os, passfd, re, sys, yaml
import netns.subprocess

# Protocol definition
#
# First key: command
# Second key: sub-command or None
# Value: pair of format strings for mandatory and optional parameters.
# The format string is a chain of "s" for string and "i" for integer

_proto_commands = {
        "QUIT": { None: ("", "") },
        "HELP": { None: ("", "") },
        "IF": {
            "LIST": ("", "i"),
            "SET":  ("iss", ""),
            "RTRN": ("ii", "")
            },
        "ADDR": {
            "LIST": ("", "i"),
            "ADD":  ("isi", "s"),
            "DEL":  ("iss", "s")
            },
        "ROUT": {
            "LIST": ("", ""),
            "ADD":  ("sisi", ""),
            "DEL":  ("sisi", "")
            },
        "PROC": {
            "CRTE": ("iib", "b*"),
            "POLL": ("i", ""),
            "WAIT": ("i", ""),
            "KILL": ("i", "i")
            },
        }
# Commands valid only after PROC CRTE
_proc_commands = {
        "HELP": { None: ("", "") },
        "QUIT": { None: ("", "") },
        "PROC": {
            "CWD":  ("b", ""),
            "ENV":  ("bb", "b*"),
            "SIN":  ("", ""),
            "SOUT": ("", ""),
            "SERR": ("", ""),
            "RUN":  ("", ""),
            "ABRT": ("", ""),
            }
        }

class Server(object):
    """Class that implements the communication protocol and dispatches calls to
    the required functions. Also works as the main loop for the slave
    process."""
    def __init__(self, fd):
        # Dictionary of valid commands
        self.commands = _proto_commands
        # Flag to stop the server
        self.closed = False
        # Print debug info
        self.debug = True
        # Dictionary to keep track of started processes
        self._children = dict()
        # Buffer and flag for PROC mode
        self._proc = None

        if hasattr(fd, "readline"):
            self.f = fd
        else:
            if hasattr(fd, "makefile"):
                self.f = fd.makefile(fd, "r+", 1) # line buffered
            else:
                self.f = os.fdopen(fd, "r+", 1)

    def abort(self, str):
        # FIXME: this should be aware of the state of the server
        # FIXME: cleanup
        self.reply(500, str)
        sys.stderr.write("Slave node aborting: %s\n" %str);
        os._exit(1)

    def reply(self, code, text):
        "Send back a reply to the client; handle multiline messages"
        if not hasattr(text, '__iter__'):
            text = [ text ]
        clean = []
        # Split lines with embedded \n
        for i in text:
            clean.extend(i.splitlines())
        for i in range(len(clean) - 1):
            self.f.write(str(code) + "-" + clean[i] + "\n")
        self.f.write(str(code) + " " + clean[-1] + "\n")
        return

    def readline(self):
        "Read a line from the socket and detect connection break-up."
        line = self.f.readline()
        if not line:
            self.closed = True
            return None
        return line.rstrip()

    def readchunk(self, size):
        "Read a chunk of data limited by size or by an empty line."
        read = 0
        res = ""

        while True:
            line = self.f.readline()
            if not line:
                self.closed = True
                return None
            if size == None and line == "\n":
                break
            read += len(line)
            res += line
            if size != None and read >= size:
                break
        return res

    def readcmd(self):
        """Main entry point: read and parse a line from the client, handle
        argument validation and return a tuple (function, command_name,
        arguments)"""
        line = self.readline()
        if not line:
            return None
        args = line.split()
        cmd1 = args[0].upper()
        if cmd1 not in self.commands:
            self.reply(500, "Unknown command %s." % cmd1)
            return None
        del args[0]

        cmd2 = None
        subcommands = self.commands[cmd1]

        if subcommands.keys() != [ None ]:
            if len(args) < 1:
                self.reply(500, "Incomplete command.")
                return None
            cmd2 = args[0].upper()
            del args[0]

        if cmd2 and cmd2 not in subcommands:
            self.reply(500, "Unknown sub-command for %s." % cmd1)
            return None

        (mandatory, optional) = subcommands[cmd2]
        argstemplate = mandatory + optional
        if cmd2:
            cmdname = "%s %s" % (cmd1, cmd2)
            funcname = "do_%s_%s" % (cmd1, cmd2)
        else:
            cmdname = cmd1
            funcname = "do_%s" % cmd1

        if not hasattr(self, funcname):
            self.reply(500, "Not implemented.")
            return None

        if len(args) < len(mandatory):
            self.reply(500, "Missing mandatory arguments for %s." % cmdname)
            return None
        if (not argstemplate or argstemplate[-1] != "*") and \
                len(args) > len(argstemplate):
            self.reply(500, "Too many arguments for %s." % cmdname)
            return None

        j = 0
        for i in range(len(args)):
            if argstemplate[j] == '*':
                j = j - 1

            if argstemplate[j] == 'i':
                try:
                    args[i] = int(args[i])
                except:
                    self.reply(500, "Invalid parameter %s: must be an integer."
                            % args[i])
                    return None
            elif argstemplate[j] == 's':
                pass
            elif argstemplate[j] == 'b':
                try:
                    if args[i][0] == '=':
                        args[i] = base64.b64decode(args[i][1:])
                except TypeError:
                    self.reply(500, "Invalid parameter: not base-64 encoded.")
                    return None
            else:
                raise RuntimeError("Invalid argument template: %s" % _argstmpl)
            j += 1

        func = getattr(self, funcname)
        return (func, cmdname, args)

    def run(self):
        """Main loop; reads commands until the server is shut down or the
        connection is terminated."""
        self.reply(220, "Hello.");
        while not self.closed:
            cmd = self.readcmd()
            if cmd == None:
                continue
            if self.debug:
                sys.stderr.write("Command: %s, args: %s\n" % (cmd[1], cmd[2]))
            cmd[0](cmd[1], *cmd[2])
        try:
            self.f.close()
        except:
            pass
        # FIXME: cleanup

    # Commands implementation

    def do_HELP(self, cmdname):
        reply = ["Available commands:"]
        for c in sorted(self.commands):
            for sc in sorted(self.commands[c]):
                if sc:
                    reply.append("%s %s" % (c, sc))
                else:
                    reply.append(c)
        self.reply(200, reply)

    def do_QUIT(self, cmdname):
        self.reply(221, "Sayounara.");
        self.closed = True

    def do_PROC_CRTE(self, cmdname, uid, gid, file, *argv):
        self._proc = { 'uid': uid, 'gid': gid, 'file': file, 'argv': argv }
        self.commands = _proc_commands
        self.reply(200, "Entering PROC mode.")

    def do_PROC_CWD(self, cmdname, dir):
        self._proc['cwd'] = dir
        self.reply(200, "CWD set to %s." % dir)

    def do_PROC_ENV(self, cmdname, *env):
        if len(env) % 2:
            self.reply(500,
                    "Invalid number of arguments for PROC ENV: must be even.")
            return
        self._proc['env'] = {}
        for i in range(len(env)/2):
            self._proc['env'][env[i * 2]] = env[i * 2 + 1]

        self.reply(200, "%d environment definition(s) read." % (len(env) / 2))

    def do_PROC_SIN(self, cmdname):
        self.reply(354,
                "Pass the file descriptor now, with '%s\\n' as payload." %
                cmdname)
        try:
            fd, payload = passfd.recvfd(len(cmdname) + 1)
            assert payload[0:len(cmdname)] == cmdname
        except:
            self.reply(500, "Invalid FD or payload.")
            raise
            return
        m = {'PROC SIN': 'stdin', 'PROC SOUT': 'stdout', 'PROC SERR': 'stderr'}
        self._proc[m[cmdname]] = fd
        self.reply(200, 'FD saved as %d.' % m[cmdname])

    # Same code for the three commands
    do_PROC_SOUT = do_PROC_SERR = do_PROC_SIN

    def do_PROC_RUN(self, cmdname):
        try:
            chld = netns.subprocess.Subprocess(**self._proc)
        except BaseException, e:
            self.reply(500, "Failure starting process: %s" % str(e))
            self._proc = None
            self.commands = _proto_commands
            return

        self._children[chld.pid] = chld
        self._proc = None
        self.commands = _proto_commands
        self.reply(200, "%d running." % chld.pid)

    def do_PROC_ABRT(self, cmdname):
        self._proc = None
        self.commands = _proto_commands
        self.reply(200, "Aborted.")

    def do_PROC_POLL(self, cmdname, pid):
        if pid not in self._children:
            self.reply(500, "Process does not exist.")
            return
        if cmdname == 'PROC POLL':
            ret = self._children[pid].poll()
        else:
            ret = self._children[pid].wait()

        if ret != None:
            del self._children[pid]
            self.reply(200, "%d exitcode." % ret)
        else:
            self.reply(450, "Not finished yet.")

    # Same code for the two commands
    do_PROC_WAIT = do_PROC_POLL

    def do_PROC_KILL(self, cmdname, pid, signal):
        if pid not in self._children:
            self.reply(500, "Process does not exist.")
            return
        if signal:
            self._children[pid].kill(signal)
        else:
            self._children[pid].kill()
        self.reply(200, "Process signalled.")

#    def do_IF_LIST(self, cmdname, ifnr = None):
#    def do_IF_SET(self, cmdname, ifnr, key, val):
#    def do_IF_RTRN(self, cmdname, ifnr, netns):
#    def do_ADDR_LIST(self, cmdname, ifnr = None):
#    def do_ADDR_ADD(self, cmdname, ifnr, address, prefixlen, broadcast = None):
#    def do_ADDR_DEL(self, cmdname, ifnr, address, prefixlen):
#    def do_ROUT_LIST(self, cmdname):
#    def do_ROUT_ADD(self, cmdname, prefix, prefixlen, nexthop, ifnr):
#    def do_ROUT_DEL(self, cmdname, prefix, prefixlen, nexthop, ifnr):


# ================

class Client(object):
    def __init__(self, fd):
        if hasattr(fd, "readline"):
            self.f = fd
        else:
            if hasattr(fd, "makefile"):
                self.f = fd.makefile(fd, "r+", 1) # line buffered
            else:
                self.f = os.fdopen(fd, "r+", 1)

    def _send_cmd(self, *args):
        s = " ".join(map(str, args)) + "\n"
        self.f.write(s)

    def _read_reply(self):
        """Reads a (possibly multi-line) response from the server. Returns a
        tuple containing (code, text)"""
        text = ""
        while True:
            line = self.f.readline().rstrip()
            if not line:
                raise RuntimeError("Protocol error, empty line received")

            m = re.search(r'^(\d{3})([ -])(.*)', line)
            if not m:
                raise RuntimeError("Protocol error, read: %s" % line)
            status = m.group(1)
            text += m.group(3)
            if m.group(2) == " ":
                break
        return (int(status), text)

    def _read_and_check_reply(self, expected = 2):
        "Reads a response and raises an exception if the code is not 2xx."
        code, text = self._read_reply()
        if code / 100 != expected:
            raise "Error on command: %d %s" % (code, text)
        return text

    def shutdown(self):
        "Tell the client to quit."
        self._send_cmd(("QUIT", ))
        self._read_and_check_reply()

    def _send_fd(self, type, fd):
        self._send_cmd("PROC", type)
        self._read_and_check_reply(3)
        passfd.sendfd(self.f.fileno(), fd, "PROC " + type)
        self._read_and_check_reply()

    def popen(self, uid, gid, file, argv = None, cwd = None, env = None,
            stdin = None, stdout = None, stderr = None):
        "Start a subprocess in the slave."

        params = ["PROC", "CRTE", uid, gid, base64.b64encode(file)]
        if argv:
            for i in argv:
                params.append(base64.b64encode(i))

        self._send_cmd(*params)
        self._read_and_check_reply()

        if cwd:
            self._send_cmd("PROC", "CWD", base64.b64encode(cwd))
            self._read_and_check_reply()

        if env:
            params = []
            for i in env:
                params.append(base64.b64encode(i))
            self._send_cmd("PROC", "ENV", params)
            self._read_and_check_reply()

        if stdin:
            self._send_fd("SIN", stdin)
        if stdout:
            self._send_fd("SOUT", stdout)
        if stderr:
            self._send_fd("SERR", stderr)

        self._send_cmd("PROC", "RUN")
        pid = self._read_and_check_reply().split()[0]

        return pid

    def poll(self, pid):
        self._send_cmd("PROC", "POLL", pid)
        code, text = self._read_reply()
        if code / 100 == 2:
            exitcode = text.split()[0]
            return exitcode
        if code / 100 == 4:
            return Null
        else:
            raise "Error on command: %d %s" % (code, text)

    def wait(self, pid):
        self._send_cmd("PROC", "WAIT", pid)
        text = self._read_and_check_reply()
        exitcode = text.split()[0]
        return exitcode

    def kill(self, pid, signal = None):
        if signal:
            self._send_cmd("PROC", "KILL", pid, signal)
        else:
            self._send_cmd("PROC", "KILL", pid)
        text = self._read_and_check_reply()

