#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

try:
    from yaml import CLoader as Loader
    from yaml import CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

import passfd, sys, yaml

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
            "WAIT": ("i", "")
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
    def __init__(self, fd):
        self.commands = _proto_commands
        self.closed = False
        self.debug = True
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
        line = self.f.readline()
        if not line:
            self.closed = True
            return None
        return line.rstrip()

    def readchunk(self, size):
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
                        args[i] = base64.b64decode(args[i])
                except:
                    self.reply(500, "Invalid parameter: not base-64 encoded.")
                    return None
            else:
                raise RuntimeError("Invalid argument template: %s" % _argstmpl)
            j += 1

        func = getattr(self, funcname)
        return (func, cmdname, args)

    def run(self):
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

    def do_IF_LIST(self, cmdname, ifnr = None):
        pass
    def do_IF_SET(self, cmdname, ifnr, key, val):
        pass
    def do_IF_RTRN(self, cmdname, ifnr, netns):
        pass
    def do_ADDR_LIST(self, cmdname, ifnr = None):
        pass
    def do_ADDR_ADD(self, cmdname, ifnr, address, prefixlen, broadcast = None):
        pass
    def do_ADDR_DEL(self, cmdname, ifnr, address, prefixlen):
        pass
    def do_ROUT_LIST(self, cmdname):
        pass
    def do_ROUT_ADD(self, cmdname, prefix, prefixlen, nexthop, ifnr):
        pass
    def do_ROUT_DEL(self, cmdname, prefix, prefixlen, nexthop, ifnr):
        pass
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

    do_PROC_SOUT = do_PROC_SERR = do_PROC_SIN

    def do_PROC_RUN(self, cmdname):
        self._proc = None
        self.commands = _proto_commands
        self.reply(200, "Aborted.")
    def do_PROC_ABRT(self, cmdname):
        self._proc = None
        self.commands = _proto_commands
        self.reply(200, "Aborted.")

    def do_PROC_POLL(self, cmdname, pid):
        pass
    def do_PROC_WAIT(self, cmdname, pid):
        pass
