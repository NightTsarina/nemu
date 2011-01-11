#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import base64, errno, os, passfd, re, select, signal, socket, sys, tempfile
import time, traceback, unshare
import netns.subprocess_, netns.iproute
from netns.environ import *

try:
    from cPickle import loads, dumps
except:
    from pickle import loads, dumps

# ============================================================================
# Server-side protocol implementation
#
# Protocol definition
# -------------------
#
# First key: command
# Second key: sub-command or None
# Value: pair of format strings for mandatory and optional parameters.
# The format string is a chain of "s" for string and "i" for integer

_proto_commands = {
        "QUIT": { None: ("", "") },
        "HELP": { None: ("", "") },
        "X11":  {
            "SET":  ("ss", ""),
            "SOCK": ("", "")
            },
        "IF": {
            "LIST": ("", "i"),
            "SET":  ("iss", "s*"),
            "RTRN": ("ii", ""),
            "DEL":  ("i", "")
            },
        "ADDR": {
            "LIST": ("", "i"),
            "ADD":  ("isi", "s"),
            "DEL":  ("iss", "s")
            },
        "ROUT": {
            "LIST": ("", ""),
            "ADD":  ("bbibii", ""),
            "DEL":  ("bbibii", "")
            },
        "PROC": {
            "CRTE": ("b", "b*"),
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
            "USER": ("b", ""),
            "CWD":  ("b", ""),
            "ENV":  ("bb", "b*"),
            "SIN":  ("", ""),
            "SOUT": ("", ""),
            "SERR": ("", ""),
            "RUN":  ("", ""),
            "ABRT": ("", ""),
            }
        }

KILL_WAIT = 3 # seconds

class Server(object):
    """Class that implements the communication protocol and dispatches calls
    to the required functions. Also works as the main loop for the slave
    process."""
    def __init__(self, rfd, wfd):
        debug("Server(0x%x).__init__()" % id(self))
        # Dictionary of valid commands
        self._commands = _proto_commands
        # Flag to stop the server
        self._closed = False
        # Set to keep track of started processes
        self._children = set()
        # Buffer and flag for PROC mode
        self._proc = None
        # temporary xauth files
        self._xauthfiles = {}
        # X11 forwarding info
        self._xfwd = None
        self._xsock = None

        self._rfd = _get_file(rfd, "r")
        self._wfd = _get_file(wfd, "w")

    def clean(self):
        for pid in self._children:
            os.kill(pid, signal.SIGTERM)
        now = time.time()
        while time.time() - now < KILL_WAIT:
            ch = []
            for pid in self._children:
                try:
                    if not netns.subprocess_.poll(pid):
                        ch.append(pid)
                except OSError, e:
                    if e.errno != errno.ECHILD:
                        raise e
            if not ch:
                break
            time.sleep(0.1)
        for pid in ch:
            warning("Killing forcefully process %d." % pid)
            os.kill(pid, signal.SIGKILL)
        for pid in ch:
            try:
                netns.subprocess_.poll(pid)
            except OSError, e:
                if e.errno != errno.ECHILD:
                    raise e

        for f in self._xauthfiles.values():
            try:
                os.unlink(f)
            except:
                pass

    def reply(self, code, text):
        "Send back a reply to the client; handle multiline messages"
        if not hasattr(text, '__iter__'):
            text = [ text ]
        clean = []
        # Split lines with embedded \n
        for i in text:
            clean.extend(i.splitlines())
        for i in range(len(clean) - 1):
            s = str(code) + "-" + clean[i] + "\n"
            self._wfd.write(s)
            debug("<Reply> %s" % s)

        s = str(code) + " " + clean[-1] + "\n"
        self._wfd.write(s)
        debug("<Reply> %s" % s)
        return

    def readline(self):
        "Read a line from the socket and detect connection break-up."
        # FIXME: should use the _eintr_wrapper from subprocess: some
        # reorganization needed first.
        while True:
            try:
                line = self._rfd.readline()
            except IOError, e:
                line = None
                if e.errno != errno.EINTR:
                    raise
            break
        if not line:
            self._closed = True
            return None
        debug("<Query> %s" % line)
        return line.rstrip()

    def readcmd(self):
        """Main entry point: read and parse a line from the client, handle
        argument validation and return a tuple (function, command_name,
        arguments)"""
        line = self.readline()
        if not line:
            return None
        args = line.split()
        cmd1 = args[0].upper()
        if cmd1 not in self._commands:
            self.reply(500, "Unknown command %s." % cmd1)
            return None
        del args[0]

        cmd2 = None
        subcommands = self._commands[cmd1]

        if subcommands.keys() != [ None ]:
            if len(args) < 1:
                self.reply(500, "Incomplete command.")
                return None
            cmd2 = args[0].upper()
            del args[0]

        if cmd2 and cmd2 not in subcommands:
            self.reply(500, "Unknown sub-command for %s: %s." % (cmd1, cmd2))
            return None

        (mandatory, optional) = subcommands[cmd2]
        argstemplate = mandatory + optional
        if cmd2:
            cmdname = "%s %s" % (cmd1, cmd2)
            funcname = "do_%s_%s" % (cmd1, cmd2)
        else:
            cmdname = cmd1
            funcname = "do_%s" % cmd1

        if not hasattr(self, funcname): # pragma: no cover
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
            elif argstemplate[j] == 'b':
                try:
                    args[i] = _db64(args[i])
                except TypeError:
                    self.reply(500, "Invalid parameter: not base-64 encoded.")
                    return None
            elif argstemplate[j] != 's': # pragma: no cover
                raise RuntimeError("Invalid argument template: %s" % _argstmpl)
            # Nothing done for "s" parameters
            j += 1

        func = getattr(self, funcname)
        debug("Command: %s, args: %s" % (cmdname, args))
        return (func, cmdname, args)

    def run(self):
        """Main loop; reads commands until the server is shut down or the
        connection is terminated."""
        self.reply(220, "Hello.");
        while not self._closed:
            cmd = self.readcmd()
            if cmd == None:
                continue
            try:
                cmd[0](cmd[1], *cmd[2])
            except:
                (t, v, tb) = sys.exc_info()
                v.child_traceback = "".join(
                        traceback.format_exception(t, v, tb))
                self.reply(550, ["# Exception data follows:",
                    _b64(dumps(v, protocol = 2))])
        try:
            self._rfd.close()
            self._wfd.close()
        except:
            pass
        self.clean()
        debug("Server(0x%x) exiting" % id(self))
        # FIXME: cleanup

    # Commands implementation

    def do_HELP(self, cmdname):
        reply = ["Available commands:"]
        for c in sorted(self._commands):
            for sc in sorted(self._commands[c]):
                if sc:
                    reply.append("%s %s" % (c, sc))
                else:
                    reply.append(c)
        self.reply(200, reply)

    def do_QUIT(self, cmdname):
        self.reply(221, "Sayounara.");
        self._closed = True

    def do_PROC_CRTE(self, cmdname, executable, *argv):
        self._proc = { 'executable': executable, 'argv': argv }
        self._commands = _proc_commands
        self.reply(200, "Entering PROC mode.")

    def do_PROC_USER(self, cmdname, user):
        self._proc['user'] = user
        self.reply(200, "Program will run as `%s'." % user)

    def do_PROC_CWD(self, cmdname, dir):
        self._proc['cwd'] = dir
        self.reply(200, "CWD set to `%s'." % dir)

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
                "Pass the file descriptor now, with `%s\\n' as payload." %
                cmdname)
        try:
            fd, payload = passfd.recvfd(self._rfd, len(cmdname) + 1)
        except (IOError, RuntimeError), e:
            self.reply(500, "Error receiving FD: %s" % str(e))
            return

        if payload[0:len(cmdname)] != cmdname:
            self.reply(500, "Invalid payload: %s." % payload)
            return

        m = {'PROC SIN': 'stdin', 'PROC SOUT': 'stdout', 'PROC SERR': 'stderr'}
        self._proc[m[cmdname]] = fd
        self.reply(200, 'FD saved as %s.' % m[cmdname])

    # Same code for the three commands
    do_PROC_SOUT = do_PROC_SERR = do_PROC_SIN

    def do_PROC_RUN(self, cmdname):
        params = self._proc
        params['close_fds'] = True # forced
        self._proc = None
        self._commands = _proto_commands

        if 'env' not in params:
            params['env'] = dict(os.environ) # copy

        xauth = None
        if self._xfwd:
            display, protoname, hexkey = self._xfwd
            user = params['user'] if 'user' in params else None
            try:
                fd, xauth = tempfile.mkstemp()
                os.close(fd)
                # stupid xauth format: needs the 'hostname' for local
                # connections
                execute([xauth_path, "-f", xauth, "add",
                    "%s/unix:%d" % (socket.gethostname(), display),
                    protoname, hexkey])
                if user:
                    user, uid, gid = netns.subprocess_.get_user(user)
                    os.chown(xauth, uid, gid)

                params['env']['DISPLAY'] = "127.0.0.1:%d" % display
                params['env']['XAUTHORITY'] = xauth

            except Exception, e:
                warning("Cannot forward X: %s" % e)
                try:
                    os.unlink(xauth)
                except:
                    pass
        else:
            if 'DISPLAY' in params['env']:
                del params['env']['DISPLAY']

        try:
            chld = netns.subprocess_.spawn(**params)
        finally:
            # I can close the fds now
            for d in ('stdin', 'stdout', 'stderr'):
                if d in params:
                    os.close(params[d])

        self._children.add(chld)
        self._xauthfiles[chld] = xauth
        self.reply(200, "%d running." % chld)

    def do_PROC_ABRT(self, cmdname):
        self._proc = None
        self._commands = _proto_commands
        self.reply(200, "Aborted.")

    def do_PROC_POLL(self, cmdname, pid):
        if pid not in self._children:
            self.reply(500, "Process does not exist.")
            return
        if cmdname == 'PROC POLL':
            ret = netns.subprocess_.poll(pid)
        else:
            ret = netns.subprocess_.wait(pid)

        if ret != None:
            self._children.remove(pid)
            if pid in self._xauthfiles:
                try:
                    os.unlink(self._xauthfiles[pid])
                except:
                    pass
                del self._xauthfiles[pid]
            self.reply(200, "%d exitcode." % ret)
        else:
            self.reply(450, "Not finished yet.")

    # Same code for the two commands
    do_PROC_WAIT = do_PROC_POLL

    def do_PROC_KILL(self, cmdname, pid, sig):
        if pid not in self._children:
            self.reply(500, "Process does not exist.")
            return
        if signal:
            os.kill(pid, sig)
        else:
            os.kill(pid, signal.SIGTERM)
        self.reply(200, "Process signalled.")

    def do_IF_LIST(self, cmdname, ifnr = None):
        if ifnr == None:
            ifdata = netns.iproute.get_if_data()[0]
        else:
            ifdata = netns.iproute.get_if(ifnr)
        self.reply(200, ["# Interface data follows.",
                _b64(dumps(ifdata, protocol = 2))])

    def do_IF_SET(self, cmdname, ifnr, *args):
        if len(args) % 2:
            self.reply(500,
                    "Invalid number of arguments for IF SET: must be even.")
            return
        d = {'index': ifnr}
        for i in range(len(args) / 2):
            d[str(args[i * 2])] = args[i * 2 + 1]

        iface = netns.iproute.interface(**d)
        netns.iproute.set_if(iface)
        self.reply(200, "Done.")

    def do_IF_RTRN(self, cmdname, ifnr, ns):
        netns.iproute.change_netns(ifnr, ns)
        self.reply(200, "Done.")

    def do_IF_DEL(self, cmdname, ifnr):
        netns.iproute.del_if(ifnr)
        self.reply(200, "Done.")

    def do_ADDR_LIST(self, cmdname, ifnr = None):
        addrdata = netns.iproute.get_addr_data()[0]
        if ifnr != None:
            addrdata = addrdata[ifnr]
        self.reply(200, ["# Address data follows.",
            _b64(dumps(addrdata, protocol = 2))])

    def do_ADDR_ADD(self, cmdname, ifnr, address, prefixlen, broadcast = None):
        if address.find(":") < 0: # crude, I know
            a = netns.iproute.ipv4address(address, prefixlen, broadcast)
        else:
            a = netns.iproute.ipv6address(address, prefixlen)
        netns.iproute.add_addr(ifnr, a)
        self.reply(200, "Done.")

    def do_ADDR_DEL(self, cmdname, ifnr, address, prefixlen):
        if address.find(":") < 0: # crude, I know
            a = netns.iproute.ipv4address(address, prefixlen, None)
        else:
            a = netns.iproute.ipv6address(address, prefixlen)
        netns.iproute.del_addr(ifnr, a)
        self.reply(200, "Done.")

    def do_ROUT_LIST(self, cmdname):
        rdata = netns.iproute.get_route_data()
        self.reply(200, ["# Routing data follows.",
            _b64(dumps(rdata, protocol = 2))])

    def do_ROUT_ADD(self, cmdname, tipe, prefix, prefixlen, nexthop, ifnr,
            metric):
        netns.iproute.add_route(netns.iproute.route(tipe, prefix, prefixlen,
            nexthop, ifnr or None, metric))
        self.reply(200, "Done.")

    def do_ROUT_DEL(self, cmdname, tipe, prefix, prefixlen, nexthop, ifnr,
            metric):
        netns.iproute.del_route(netns.iproute.route(tipe, prefix, prefixlen,
            nexthop, ifnr or None, metric))
        self.reply(200, "Done.")

    def do_X11_SET(self, cmdname, protoname, hexkey):
        if not xauth_path:
            self.reply(500, "Impossible to forward X: xauth not present")
            return
        skt, port = None, None
        try:
            skt, port = find_listen_port(min_port = 6010, max_port = 6099)
        except:
            self.reply(500, "Cannot allocate a port for X forwarding.")
            return
        display = port - 6000

        self.reply(200, "Socket created on port %d. Use X11 SOCK to get the "
                "file descriptor "
                "(fixed 1-byte payload before protocol response).")
        self._xfwd = display, protoname, hexkey
        self._xsock = skt

    def do_X11_SOCK(self, cmdname):
        if not self._xsock:
            self.reply(500, "X forwarding not set up.")
            return
        # Needs to be a separate command to handle synch & buffering issues
        try:
            passfd.sendfd(self._wfd, self._xsock.fileno(), "1")
        except:
            # need to fill the buffer on the other side, nevertheless
            self._wfd.write("1")
            self.reply(500, "Error sending file descriptor.")
            return
        self._xsock = None
        self.reply(200, "Will set up X forwarding.")

# ============================================================================
#
# Client-side protocol implementation.
#
class Client(object):
    """Client-side implementation of the communication protocol. Acts as a RPC
    service."""
    def __init__(self, rfd, wfd):
        debug("Client(0x%x).__init__()" % id(self))
        self._rfd = _get_file(rfd, "r")
        self._wfd = _get_file(wfd, "w")
        self._forwarder = None
        # Wait for slave to send banner
        self._read_and_check_reply()

    def __del__(self):
        debug("Client(0x%x).__del__()" % id(self))
        self.shutdown()

    def _send_cmd(self, *args):
        if not self._wfd:
            raise RuntimeError("Client already shut down.")
        s = " ".join(map(str, args)) + "\n"
        self._wfd.write(s)

    def _read_reply(self):
        """Reads a (possibly multi-line) response from the server. Returns a
        tuple containing (code, text)"""
        if not self._rfd:
            raise RuntimeError("Client already shut down.")
        text = []
        while True:
            line = self._rfd.readline().rstrip()
            if not line:
                raise RuntimeError("Protocol error, empty line received")

            m = re.search(r'^(\d{3})([ -])(.*)', line)
            if not m:
                raise RuntimeError("Protocol error, read: %s" % line)
            status = m.group(1)
            text.append(m.group(3))
            if m.group(2) == " ":
                break
        return (int(status), "\n".join(text))

    def _read_and_check_reply(self, expected = 2):
        """Reads a response and raises an exception if the first digit of the
        code is not the expected value. If expected is not specified, it
        defaults to 2."""
        code, text = self._read_reply()
        if code == 550: # exception
            e = loads(_db64(text.partition("\n")[2]))
            raise e
        if code / 100 != expected:
            raise RuntimeError("Error from slave: %d %s" % (code, text))
        return text

    def shutdown(self):
        "Tell the client to quit."
        if not self._wfd:
            return
        debug("Client(0x%x).shutdown()" % id(self))

        self._send_cmd("QUIT")
        self._read_and_check_reply()
        self._rfd.close()
        self._rfd = None
        self._wfd.close()
        self._wfd = None
        if self._forwarder:
            os.kill(self._forwarder, signal.SIGTERM)
            self._forwarder = None

    def _send_fd(self, name, fd):
        "Pass a file descriptor"
        self._send_cmd("PROC", name)
        self._read_and_check_reply(3)
        try:
            passfd.sendfd(self._wfd, fd, "PROC " + name)
        except:
            # need to fill the buffer on the other side, nevertheless
            self._wfd.write("=" * (len(name) + 5) + "\n")
            # And also read the expected error
            self._read_and_check_reply(5)
            raise
        self._read_and_check_reply()

    def spawn(self, argv, executable = None,
            stdin = None, stdout = None, stderr = None,
            cwd = None, env = None, user = None):
        """Start a subprocess in the slave; the interface resembles
        subprocess.Popen, but with less functionality. In particular
        stdin/stdout/stderr can only be None or a open file descriptor.
        See netns.subprocess_.spawn for details."""

        if executable == None:
            executable = argv[0]
        params = ["PROC", "CRTE", _b64(executable)]
        for i in argv:
            params.append(_b64(i))

        self._send_cmd(*params)
        self._read_and_check_reply()

        # After this, if we get an error, we have to abort the PROC
        try:
            if user != None:
                self._send_cmd("PROC", "USER", _b64(user))
                self._read_and_check_reply()

            if cwd != None:
                self._send_cmd("PROC", "CWD", _b64(cwd))
                self._read_and_check_reply()

            if env != None:
                params = []
                for k, v in env.items():
                    params.extend([_b64(k), _b64(v)])
                self._send_cmd("PROC", "ENV", *params)
                self._read_and_check_reply()

            if stdin != None:
                self._send_fd("SIN", stdin)
            if stdout != None:
                self._send_fd("SOUT", stdout)
            if stderr != None:
                self._send_fd("SERR", stderr)
        except:
            self._send_cmd("PROC", "ABRT")
            self._read_and_check_reply()
            raise

        self._send_cmd("PROC", "RUN")
        pid = int(self._read_and_check_reply().split()[0])

        return pid

    def poll(self, pid):
        """Equivalent to Popen.poll(), checks if the process has finished.
        Returns the exitcode if finished, None otherwise."""
        self._send_cmd("PROC", "POLL", pid)
        code, text = self._read_reply()
        if code / 100 == 2:
            exitcode = int(text.split()[0])
            return exitcode
        if code / 100 == 4:
            return None
        else:
            raise "Error on command: %d %s" % (code, text)

    def wait(self, pid):
        """Equivalent to Popen.wait(). Waits for the process to finish and
        returns the exitcode."""
        self._send_cmd("PROC", "WAIT", pid)
        text = self._read_and_check_reply()
        exitcode = int(text.split()[0])
        return exitcode

    def signal(self, pid, sig = signal.SIGTERM):
        """Equivalent to Popen.send_signal(). Sends a signal to the child
        process; signal defaults to SIGTERM."""
        if sig:
            self._send_cmd("PROC", "KILL", pid, sig)
        else:
            self._send_cmd("PROC", "KILL", pid)
        self._read_and_check_reply()

    def get_if_data(self, ifnr = None):
        if ifnr:
            self._send_cmd("IF", "LIST", ifnr)
        else:
            self._send_cmd("IF", "LIST")
        data = self._read_and_check_reply()
        return loads(_db64(data.partition("\n")[2]))

    def set_if(self, interface):
        cmd = ["IF", "SET", interface.index]
        for k in interface.changeable_attributes:
            v = getattr(interface, k)
            if v != None:
                cmd += [k, str(v)]

        self._send_cmd(*cmd)
        self._read_and_check_reply()

    def del_if(self, ifnr):
        self._send_cmd("IF", "DEL", ifnr)
        self._read_and_check_reply()

    def change_netns(self, ifnr, netns):
        self._send_cmd("IF", "RTRN", ifnr, netns)
        self._read_and_check_reply()

    def get_addr_data(self, ifnr = None):
        if ifnr:
            self._send_cmd("ADDR", "LIST", ifnr)
        else:
            self._send_cmd("ADDR", "LIST")
        data = self._read_and_check_reply()
        return loads(_db64(data.partition("\n")[2]))

    def add_addr(self, ifnr, address):
        if hasattr(address, "broadcast") and address.broadcast:
            self._send_cmd("ADDR", "ADD", ifnr, address.address,
                    address.prefix_len, address.broadcast)
        else:
            self._send_cmd("ADDR", "ADD", ifnr, address.address,
                    address.prefix_len)
        self._read_and_check_reply()

    def del_addr(self, ifnr, address):
        self._send_cmd("ADDR", "DEL", ifnr, address.address, address.prefix_len)
        self._read_and_check_reply()

    def get_route_data(self):
        self._send_cmd("ROUT", "LIST")
        data = self._read_and_check_reply()
        return loads(_db64(data.partition("\n")[2]))

    def add_route(self, route):
        self._add_del_route("ADD", route)

    def del_route(self, route):
        self._add_del_route("DEL", route)

    def _add_del_route(self, action, route):
        args = ["ROUT", action, _b64(route.tipe), _b64(route.prefix),
                route.prefix_len or 0, _b64(route.nexthop),
                route.interface or 0, route.metric or 0]
        self._send_cmd(*args)
        self._read_and_check_reply()

    def set_x11(self, protoname, hexkey):
        # Returns a socket ready to accept() connections
        self._send_cmd("X11", "SET", protoname, hexkey)
        self._read_and_check_reply()
        # Receive the socket
        self._send_cmd("X11", "SOCK")
        fd, payload = passfd.recvfd(self._rfd, 1)
        self._read_and_check_reply()
        skt = socket.fromfd(fd, socket.AF_INET, socket.SOCK_DGRAM)
        os.close(fd) # fromfd dup()'s
        return skt

    def enable_x11_forwarding(self):
        xinfo = _parse_display()
        if not xinfo:
            raise RuntimeError("Impossible to forward X: DISPLAY variable not "
                    "set or invalid")
        if not xauth_path:
            raise RuntimeError("Impossible to forward X: xauth not present")
        auth = backticks([xauth_path, "list", os.environ["DISPLAY"]])
        match = re.match(r"\S+\s+(\S+)\s+(\S+)\n", auth)
        if not match:
            raise RuntimeError("Impossible to forward X: invalid DISPLAY")
        protoname, hexkey = match.groups()

        server = self.set_x11(protoname, hexkey)
        self._forwarder = _spawn_x11_forwarder(server, *xinfo)

def _b64(text):
    if text == None:
        # easier this way
        text = ''
    text = str(text)
    if len(text) == 0 or filter(lambda x: ord(x) <= ord(" ") or
            ord(x) > ord("z") or x == "=", text):
        return "=" + base64.b64encode(text)
    else:
        return text

def _db64(text):
    if not text or text[0] != '=':
        return text
    return base64.b64decode(text[1:])

def _get_file(fd, mode):
    # Since fdopen insists on closing the fd on destruction, I need to dup()
    if hasattr(fd, "fileno"):
        nfd = os.dup(fd.fileno())
    else:
        nfd = os.dup(fd)
    return os.fdopen(nfd, mode, 1)

def _parse_display():
    if "DISPLAY" not in os.environ:
        return None
    dpy = os.environ["DISPLAY"]
    match = re.search(r"^(.*):(\d+)(?:\.(\d+))$", dpy)
    if not match:
        return None
    if match.group(1):
        sock = (socket.AF_INET, socket.SOCK_STREAM, 0)
        addr = (match.group(1), 6000 + int(match.group(2)))
    else:
        sock = (socket.AF_UNIX, socket.SOCK_STREAM, 0)
        addr = ("/tmp/.X11-unix/X%d" % int(match.group(2)))
    return sock, addr

def _spawn_x11_forwarder(server, xsock, xaddr):
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.listen(10) # arbitrary
    pid = os.fork()
    if pid:
        return pid
    # XXX: clear signals, etc
    try:
        _x11_forwarder(server, xsock, xaddr)
    except:
        traceback.print_exc(file=sys.stderr)
    os._exit(1)

def _x11_forwarder(server, xsock, xaddr):
    def clean(idx, toread, fd):
        # silently discards any buffer!
        fd1 = fd
        fd2 = idx[fd]["wr"]
        try:
            fd1.close()
        except:
            pass
        try:
            fd2.close()
        except:
            pass
        del idx[fd1]
        if fd1 in toread:
            toread.remove(fd1)
        del idx[fd2]
        if fd2 in toread:
            toread.remove(fd2)

    toread = set([server])
    idx = {}
    while(True):
        towrite = [x["wr"] for x in idx.values() if x["buf"]]
        (rr, wr, er) = select.select(toread, towrite, [])

        if server in rr:
            xconn = socket.socket(*xsock)
            xconn.connect(xaddr)
            client, addr = server.accept()
            toread.add(client)
            toread.add(xconn)
            idx[client] = {
                    "rd":       client,
                    "wr":       xconn,
                    "buf":      [],
                    "closed":   False
                    }
            idx[xconn] = {
                    "rd":       xconn,
                    "wr":       client,
                    "buf":      [],
                    "closed":   False
                    }
            continue

        for fd in rr:
            chan = idx[fd]
            try:
                s = os.read(fd.fileno(), 4096)
            except OSError, e:
                if e.errno == errno.ECONNRESET:
                    clean(idx, toread, fd)
                    continue
                elif e.errno == errno.EINTR:
                    continue
                else:
                    raise

            if s == "":
                # fd closed for read
                toread.remove(fd)
                chan["closed"] = True
                if not chan["buf"]:
                    # close the writing side
                    try:
                        chan["wr"].shutdown(socket.SHUT_WR)
                    except:
                        pass # might fail sometimes
            else:
                chan["buf"].append(s)

        for fd in wr:
            chan = idx[idx[fd]["wr"]]
            try:
                x = os.write(fd.fileno(), chan["buf"][0])
            except OSError, e:
                if e.errno == errno.EINTR:
                    continue
                if e.errno == errno.EPIPE or e.errno == errno.ECONNRESET:
                    clean(idx, toread, fd)
                    continue
                raise

            if x < len(chan["buf"][0]):
                chan["buf"][0] = chan["buf"][x:]
            else:
                del chan["buf"][0]
            if not chan["buf"] and chan["closed"]:
                chan["wr"].shutdown(socket.SHUT_WR)
                chan["buf"] = None

        # clean-up
        for chan in idx.values():
            if chan["rd"] not in idx:
                # already deleted
                continue
            twin = idx[chan["wr"]]
            if not chan["closed"] or chan["buf"] or not twin["closed"] \
                    or twin["buf"]:
                continue
            clean(idx, toread, chan["rd"])
