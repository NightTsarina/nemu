# vim:ts=4:sw=4:et:ai:sts=4
# -*- coding: utf-8 -*-

# Copyright 2010, 2011 INRIA
# Copyright 2011 Martina Ferrari <tina@tina.pm>
#
# This file is part of Nemu.
#
# Nemu is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2, as published by the Free
# Software Foundation.
#
# Nemu is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# Nemu.  If not, see <http://www.gnu.org/licenses/>.

import fcntl, grp, os, pickle, pwd, signal, select, sys, time, traceback
from nemu.environ import eintr_wrapper

__all__ = [ 'PIPE', 'STDOUT', 'Popen', 'Subprocess', 'spawn', 'wait', 'poll',
        'get_user', 'system', 'backticks', 'backticks_raise' ]

# User-facing interfaces

KILL_WAIT = 3 # seconds

class Subprocess(object):
    """Class that allows the execution of programs inside a nemu Node. This is
    the base class for all process operations, Popen provides a more high level
    interface."""
    # FIXME
    default_user = None
    def __init__(self, node, argv, executable = None,
            stdin = None, stdout = None, stderr = None,
            shell = False, cwd = None, env = None, user = None):
        self._slave = node._slave
        """Forks and execs a program, with stdio redirection and user
        switching.
        
        A nemu Node to run the program is is specified as the first parameter.

        The program is specified by `executable', if it does not contain any
        slash, the PATH environment variable is used to search for the file.

        The `user` parameter, if not None, specifies a user name to run the
        command as, after setting its primary and secondary groups. If a
        numerical UID is given, a reverse lookup is performed to find the user
        name and then set correctly the groups.

        To run the program in a different directory than the current one, it
        should be set in `cwd'.

        If specified, `env' replaces the caller's environment with the
        dictionary provided.

        The standard input, output, and error of the created process will be
        redirected to the file descriptors specified by `stdin`, `stdout`, and
        `stderr`, respectively. These parameters must be open file objects,
        integers, or None (for no redirection). Note that the descriptors will
        not be closed by this class.
        
        Exceptions occurred while trying to set up the environment or executing
        the program are propagated to the parent."""

        if user == None:
            user = Subprocess.default_user

        if isinstance(argv, str):
            argv = [ argv ]
        if shell:
            argv = [ '/bin/sh', '-c' ] + argv
        
        # Initialize attributes that would be used by the destructor if spawn
        # fails
        self._pid = self._returncode = None
        # confusingly enough, to go to the function at the top of this file,
        # I need to call it thru the communications protocol: remember that
        # happens in another process!
        self._pid = self._slave.spawn(argv, executable = executable,
                stdin = stdin, stdout = stdout, stderr = stderr,
                cwd = cwd, env = env, user = user)

        node._add_subprocess(self)

    @property
    def pid(self):
        """The real process ID of this subprocess."""
        return self._pid

    def poll(self):
        """Checks status of program, returns exitcode or None if still running.
        See Popen.poll."""
        if self._returncode == None:
            self._returncode = self._slave.poll(self._pid)
        return self.returncode

    def wait(self):
        """Waits for program to complete and returns the exitcode.
        See Popen.wait"""
        if self._returncode == None:
            self._returncode = self._slave.wait(self._pid)
        return self.returncode

    def signal(self, sig = signal.SIGTERM):
        """Sends a signal to the process."""
        if self._returncode == None:
            self._slave.signal(self._pid, sig)

    @property
    def returncode(self):
        """When the program has finished (and has been waited for with
        communicate, wait, or poll), returns the signal that killed the
        program, if negative; otherwise, it is the exit code of the program.
        """
        if self._returncode == None:
            return None
        if os.WIFSIGNALED(self._returncode):
            return -os.WTERMSIG(self._returncode)
        if os.WIFEXITED(self._returncode):
            return os.WEXITSTATUS(self._returncode)
        raise RuntimeError("Invalid return code") # pragma: no cover

    def __del__(self):
        self.destroy()
    def destroy(self):
        if self._returncode != None or self._pid == None:
            return
        self.signal()
        now = time.time()
        while time.time() - now < KILL_WAIT:
            if self.poll() != None:
                return
            time.sleep(0.1)
        sys.stderr.write("WARNING: killing forcefully process %d.\n" %
                self._pid)
        self.signal(signal.SIGKILL)
        self.wait()

PIPE = -1
STDOUT = -2
class Popen(Subprocess):
    """Higher-level interface for executing processes, that tries to emulate
    the stdlib's subprocess.Popen as much as possible."""

    def __init__(self, node, argv, executable = None,
            stdin = None, stdout = None, stderr = None, bufsize = 0,
            shell = False, cwd = None, env = None, user = None):
        """As in Subprocess, `node' specifies the nemu Node to run in.

        The `stdin', `stdout', and `stderr' parameters also accept the special
        values subprocess.PIPE or subprocess.STDOUT. Check the stdlib's
        subprocess module for more details. `bufsize' specifies the buffer size
        for the buffered IO provided for PIPE'd descriptors.
        """

        self.stdin = self.stdout = self.stderr = None
        self._pid = self._returncode = None
        fdmap = { "stdin": stdin, "stdout": stdout, "stderr": stderr }
        # if PIPE: all should be closed at the end
        for k, v in fdmap.items():
            if v == None:
                continue
            if v == PIPE:
                r, w = os.pipe()
                if k == "stdin":
                    self.stdin = os.fdopen(w, 'wb', bufsize)
                    fdmap[k] = r
                else:
                    setattr(self, k, os.fdopen(r, 'rb', bufsize))
                    fdmap[k] = w
            elif isinstance(v, int):
                pass
            else:
                fdmap[k] = v.fileno()
        if stderr == STDOUT:
            fdmap['stderr'] = fdmap['stdout']

        super(Popen, self).__init__(node, argv, executable = executable,
                stdin = fdmap['stdin'], stdout = fdmap['stdout'],
                stderr = fdmap['stderr'],
                shell = shell, cwd = cwd, env = env, user = user)

        # Close pipes, they have been dup()ed to the child
        for k, v in fdmap.items():
            if getattr(self, k) != None:
                eintr_wrapper(os.close, v)

    def communicate(self, input = None):
        """See Popen.communicate."""
        # FIXME: almost verbatim from stdlib version, need to be removed or
        # something
        wset = []
        rset = []
        err = None
        out = None
        if self.stdin != None:
            self.stdin.flush()
            if input:
                wset.append(self.stdin)
            else:
                self.stdin.close()
        if self.stdout != None:
            rset.append(self.stdout)
            out = []
        if self.stderr != None:
            rset.append(self.stderr)
            err = []

        offset = 0
        while rset or wset:
            r, w, x = select.select(rset, wset, [])
            if self.stdin in w:
                wrote = os.write(self.stdin.fileno(),
                        #buffer(input, offset, select.PIPE_BUF))
                        buffer(input, offset, 512)) # XXX: py2.7
                offset += wrote
                if offset >= len(input):
                    self.stdin.close()
                    wset = []
            for i in self.stdout, self.stderr:
                if i in r:
                    d = os.read(i.fileno(), 1024) # No need for eintr wrapper
                    if d == "":
                        i.close
                        rset.remove(i)
                    else:
                        if i == self.stdout:
                            out.append(d)
                        else:
                            err.append(d)

        if out != None:
            out = ''.join(out)
        if err != None:
            err = ''.join(err)
        self.wait()
        return (out, err)

def system(node, args):
    """Emulates system() function, if `args' is an string, it uses `/bin/sh' to
    exexecute it, otherwise is interpreted as the argv array to call execve."""
    shell = isinstance(args, str)
    return Popen(node, args, shell = shell).wait()

def backticks(node, args):
    """Emulates shell backticks, if `args' is an string, it uses `/bin/sh' to
    exexecute it, otherwise is interpreted as the argv array to call execve."""
    shell = isinstance(args, str)
    return Popen(node, args, shell = shell, stdout = PIPE).communicate()[0]

def backticks_raise(node, args):
    """Emulates shell backticks, if `args' is an string, it uses `/bin/sh' to
    exexecute it, otherwise is interpreted as the argv array to call execve.
    Raises an RuntimeError if the return value is not 0."""
    shell = isinstance(args, str)
    p = Popen(node, args, shell = shell, stdout = PIPE)
    out = p.communicate()[0]
    ret = p.returncode
    if ret > 0:
        raise RuntimeError("Command failed with return code %d." % ret)
    if ret < 0:
        raise RuntimeError("Command killed by signal %d." % -ret)
    return out

# =======================================================================
#
# Server-side code, called from nemu.protocol.Server

def spawn(executable, argv = None, cwd = None, env = None, close_fds = False,
        stdin = None, stdout = None, stderr = None, user = None):
    """Internal function that performs all the dirty work for Subprocess, Popen
    and friends. This is executed in the slave process, directly from the
    protocol.Server class.

    Parameters have the same meaning as the stdlib's subprocess.Popen class,
    with one addition: the `user` parameter, if not None, specifies a user name
    to run the command as, after setting its primary and secondary groups. If a
    numerical UID is given, a reverse lookup is performed to find the user name
    and then set correctly the groups.

    When close_fds is True, it closes all file descriptors bigger than 2.  It
    can also be an iterable of file descriptors to close after fork.

    Note that 'std{in,out,err}' must be None, integers, or file objects, PIPE
    is not supported here. Also, the original descriptors are not closed.
    """
    userfd = [stdin, stdout, stderr]
    filtered_userfd = filter(lambda x: x != None and x >= 0, userfd)
    for i in range(3):
        if userfd[i] != None and not isinstance(userfd[i], int):
            userfd[i] = userfd[i].fileno() # pragma: no cover

    # Verify there is no clash
    assert not (set([0, 1, 2]) & set(filtered_userfd))

    if user != None:
        user, uid, gid = get_user(user)
        home = pwd.getpwuid(uid)[5]
        groups = [x[2] for x in grp.getgrall() if user in x[3]]
        if not env:
            env = dict(os.environ)
        env['HOME'] = home
        env['USER'] = user

    (r, w) = os.pipe()
    pid = os.fork()
    if pid == 0: # pragma: no cover
        # coverage doesn't seem to understand fork
        try:
            # Set up stdio piping
            for i in range(3):
                if userfd[i] != None and userfd[i] >= 0:
                    os.dup2(userfd[i], i)
                    if userfd[i] != i and userfd[i] not in userfd[0:i]:
                        eintr_wrapper(os.close, userfd[i]) # only in child!

            # Set up special control pipe
            eintr_wrapper(os.close, r)
            flags = fcntl.fcntl(w, fcntl.F_GETFD)
            fcntl.fcntl(w, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)

            if close_fds == True:
                for i in xrange(3, MAXFD):
                    if i != w:
                        try:
                            os.close(i)
                        except:
                            pass
            elif close_fds != False:
                for i in close_fds:
                    os.close(i)

            # changing process group id
            # (it is necessary to kill the forked subprocesses)
            os.setpgrp()

            if user != None:
                # Change user
                os.setgid(gid)
                os.setgroups(groups)
                os.setuid(uid)
            if cwd != None:
                os.chdir(cwd)
            if not argv:
                argv = [ executable ]
            if '/' in executable: # Should not search in PATH
                if env != None:
                    os.execve(executable, argv, env)
                else:
                    os.execv(executable, argv)
            else: # use PATH
                if env != None:
                    os.execvpe(executable, argv, env)
                else:
                    os.execvp(executable, argv)
            raise RuntimeError("Unreachable reached!")
        except:
            try:
                (t, v, tb) = sys.exc_info()
                # Got the child_traceback attribute trick from Python's
                # subprocess.py
                v.child_traceback = "".join(
                        traceback.format_exception(t, v, tb))
                eintr_wrapper(os.write, w, pickle.dumps(v))
                eintr_wrapper(os.close, w)
                #traceback.print_exc()
            except:
                traceback.print_exc()
            os._exit(1)

    eintr_wrapper(os.close, w)

    # read EOF for success, or a string as error info
    s = ""
    while True:
        s1 = eintr_wrapper(os.read, r, 4096)
        if s1 == "":
            break
        s += s1
    eintr_wrapper(os.close, r)

    if s == "":
        return pid

    # It was an error
    eintr_wrapper(os.waitpid, pid, 0)
    exc = pickle.loads(s)
    # XXX: sys.excepthook
    #print exc.child_traceback
    raise exc

def poll(pid):
    """Check if the process already died. Returns the exit code or None if
    the process is still alive."""
    r = os.waitpid(pid, os.WNOHANG)
    if r[0]:
        return r[1]
    return None

def wait(pid):
    """Wait for process to die and return the exit code."""
    return eintr_wrapper(os.waitpid, pid, 0)[1]

def get_user(user):
    "Take either an username or an uid, and return a tuple (user, uid, gid)."
    if str(user).isdigit():
        uid = int(user)
        try:
            user = pwd.getpwuid(uid)[0]
        except KeyError:
            raise ValueError("UID %d does not exist" % int(user))
    else:
        try:
            uid = pwd.getpwnam(str(user))[2]
        except KeyError:
            raise ValueError("User %s does not exist" % str(user))
    gid = pwd.getpwuid(uid)[3]
    return user, uid, gid

# internal stuff, do not look!

try:
    MAXFD = os.sysconf("SC_OPEN_MAX")
except: # pragma: no cover
    MAXFD = 256


