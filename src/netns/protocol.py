#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

try:
    from yaml import CLoader as Loader
    from yaml import CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

import sys, yaml

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
            "CRTE": ("", "i"),
            "POLL": ("i", ""),
            "WAIT": ("i", "")
            },
        }
# Commands valid only after PROC CRTE
_proc_commands = {
        "HELP": { None: ("", "") },
        "QUIT": { None: ("", "") },
        "PROC": {
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
        if len(args) > len(argstemplate):
            self.reply(500, "Too many arguments for %s." % cmdname)
            return None

        for i in range(len(args)):
            if argstemplate[i] == 'i':
                try:
                    args[i] = int(args[i])
                except:
                    self.reply(500, "Invalid parameter %s: must be an integer."
                            % args[i])
                    return None
            elif argstemplate[i] == 's':
                pass
            else:
                raise RuntimeError("Invalid argument template: %s" % _argstmpl)

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
    def do_PROC_CRTE(self, cmdname, argslen = None):
        if argslen:
            self.reply(354, "Go ahead, reading %d bytes." % argslen)
        else:
            self.reply(354, "Go ahead, enter an empty line to finish.")
        argsstr = self.readchunk(argslen)
        if argsstr == None: # connection closed
            return
        if not argsstr:
            self.reply(500, "Missing parameters.")
            return
        try:
            args = yaml.load(argsstr, Loader = Loader)
        except BaseException, e:
            self.reply(500, "Cannot decode parameters: %s" % e)
            return

        if not hasattr(args, "items"):
            self.reply(500, "Invalid parameters.")
            return

        valid_params = { 'cwd': str, 'exec': str, 'args': list, 'uid': int,
                'gid': int }
        for (k, v) in args.items():
            try:
                args[k] = valid_params[k](args[k])
            except:
                self.reply(500, "Invalid parameter: %s" % k)
                return

        required_params = [ 'exec', 'args', 'uid', 'gid' ]
        for i in required_params:
            if i not in args:
                self.reply(500, "Missing required parameter: %s" % i)
                return

        if self.debug:
            sys.stderr.write("Arguments for PROC CRTE: %s\n" % str(args))
        self.reply(200, "Entering PROC mode.")

        self._proc_args = args
        self.commands = _proc_commands

    def do_PROC_POLL(self, cmdname, pid):
        pass
    def do_PROC_WAIT(self, cmdname, pid):
        pass
    def do_PROC_SIN(self, cmdname):
        pass
    def do_PROC_SOUT(self, cmdname):
        pass
    def do_PROC_SERR(self, cmdname):
        pass
    def do_PROC_RUN(self, cmdname):
        self.reply(200, "Aborted.")
        self.commands = _proto_commands
    def do_PROC_ABRT(self, cmdname):
        self.reply(200, "Aborted.")
        self.commands = _proto_commands

