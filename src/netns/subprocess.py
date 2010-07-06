#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import fcntl, grp, os, pickle, pwd, signal, select, sys, traceback

__all__ = [ 'PIPE', 'STDOUT', 'Popen', 'Subprocess', 'spawn', 'wait', 'poll',
        'system', 'backticks', 'backticks_raise' ]

# User-facing interfaces

class Subprocess(object):
    """Class that allows the execution of programs inside a netns Node. This is
    the base class for all process operations, Popen provides a more high level
    interface."""
    # FIXME
    default_user = None
    def __init__(self, node, executable, argv = None, cwd = None, env = None,
            stdin = None, stdout = None, stderr = None, user = None):
        self._slave = node._slave
        """Forks and execs a program, with stdio redirection and user
        switching.
        
        A netns Node to run the program is is specified as the first parameter.

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

        # confusingly enough, to go to the function at the top of this file,
        # I need to call it thru the communications protocol: remember that
        # happens in another process!
        self._pid = self._slave.spawn(executable, argv = argv, cwd = cwd,
                env = env, stdin = stdin, stdout = stdout, stderr = stderr,
                user = user)

        node._add_subprocess(self)
        self._returncode = None

    @property
    def pid(self):
        """The real process ID of this subprocess."""
        return self._pid

    def poll(self):
        """Checks status of program, returns exitcode or None if still running.
        See Popen.poll."""
        r = self._slave.poll(self._pid)
        if r != None:
            del self._pid
            self._returncode = r
        return self.returncode

    def wait(self):
        """Waits for program to complete and returns the exitcode.
        See Popen.wait"""
        self._returncode = self._slave.wait(self._pid)
        del self._pid
        return self.returncode

    def signal(self, sig = signal.SIGTERM):
        """Sends a signal to the process."""
        return self._slave.signal(self._pid, sig)

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
        raise RuntimeError("Invalid return code")

    # FIXME: do we have any other way to deal with this than having explicit
    # destroy?
    def destroy(self):
        pass

PIPE = -1
STDOUT = -2
class Popen(Subprocess):
    """Higher-level interface for executing processes, that tries to emulate
    the stdlib's subprocess.Popen as much as possible."""

    def __init__(self, node, executable, argv = None, cwd = None, env = None,
            stdin = None, stdout = None, stderr = None, user = None,
            bufsize = 0):
        """As in Subprocess, `node' specifies the netns Node to run in.

        The `stdin', `stdout', and `stderr' parameters also accept the special
        values subprocess.PIPE or subprocess.STDOUT. Check the stdlib's
        subprocess module for more details. `bufsize' specifies the buffer size
        for the buffered IO provided for PIPE'd descriptors.
        """

        self.stdin = self.stdout = self.stderr = None
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

        super(Popen, self).__init__(node, executable, argv = argv, cwd = cwd,
                env = env, stdin = fdmap['stdin'], stdout = fdmap['stdout'],
                stderr = fdmap['stderr'], user = user)

        # Close pipes, they have been dup()ed to the child
        for k, v in fdmap.items():
            if getattr(self, k) != None:
                _eintr_wrapper(os.close, v)

        #self.universal_newlines = False # compat with subprocess.communicate

    # No need to reinvent the wheel: damnit, stupid python namespace handling
    # won't allow me to reference another module called subprocess...
    #communicate = subprocess.communicate
    #_communicate = subprocess._communicate
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
    if isinstance(args, str):
        args = [ '/bin/sh', '/bin/sh', '-c', args ]
    return Popen(node, args[0], args[1:]).wait()

def backticks(node, args):
    """Emulates shell backticks, if `args' is an string, it uses `/bin/sh' to
    exexecute it, otherwise is interpreted as the argv array to call execve."""
    if isinstance(args, str):
        args = [ '/bin/sh', '/bin/sh', '-c', args ]
    return Popen(node, args[0], args[1:], stdout = PIPE).communicate()[0]

def backticks_raise(node, args):
    """Emulates shell backticks, if `args' is an string, it uses `/bin/sh' to
    exexecute it, otherwise is interpreted as the argv array to call execve.
    Raises an RuntimeError if the return value is not 0."""
    if isinstance(args, str):
        args = [ '/bin/sh', '/bin/sh', '-c', args ]
    p = Popen(node, args[0], args[1:], stdout = PIPE)
    out = p.communicate()[0]
    if p.returncode > 0:
        raise RuntimeError("Command failed with return code %d." %
                p.returncode)
    if p.returncode < 0:
        raise RuntimeError("Command killed by signal %d." % -p.returncode)
    return out

# =======================================================================
#
# Server-side code, called from netns.protocol.Server

def spawn(executable, argv = None, cwd = None, env = None, stdin = None,
        stdout = None, stderr = None, close_fds = False, user = None):
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
            userfd[i] = userfd[i].fileno()

    # Verify there is no clash
    assert not (set([0, 1, 2]) & set(filtered_userfd))

    if user != None:
        if str(user).isdigit():
            uid = int(user)
            try:
                user = pwd.getpwuid(uid)[0]
            except:
                raise ValueError("UID %d does not exist" % int(user))
        else:
            try:
                uid = pwd.getpwnam(str(user))[2]
            except:
                raise ValueError("User %s does not exist" % str(user))

        gid = pwd.getpwuid(uid)[3]
        groups = [x[2] for x in grp.getgrall() if user in x[3]]

    (r, w) = os.pipe()
    pid = os.fork()
    if pid == 0:
        try:
            # Set up stdio piping
            for i in range(3):
                if userfd[i] != None and userfd[i] >= 0:
                    os.dup2(userfd[i], i)
                    if userfd[i] != i and userfd[i] not in userfd[0:i]:
                        _eintr_wrapper(os.close, userfd[i]) # only in child!

            # Set up special control pipe
            _eintr_wrapper(os.close, r)
            flags = fcntl.fcntl(w, fcntl.F_GETFD)
            fcntl.fcntl(w, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)

            if close_fds == False:
                pass
            elif close_fds == True:
                for i in xrange(3, MAXFD):
                    if i != w:
                        try:
                            os.close(i)
                        except:
                            pass
            else:
                for i in close_fds:
                    os.close(i)

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
                _eintr_wrapper(os.write, w, pickle.dumps(v))
                _eintr_wrapper(os.close, w)
                #traceback.print_exc()
            except:
                traceback.print_exc()
            os._exit(1)

    _eintr_wrapper(os.close, w)

    # read EOF for success, or a string as error info
    s = ""
    while True:
        s1 = _eintr_wrapper(os.read, r, 4096)
        if s1 == "":
            break
        s += s1
    _eintr_wrapper(os.close, r)

    if s == "":
        return pid

    # It was an error
    _eintr_wrapper(os.waitpid, pid, 0)
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
    return _eintr_wrapper(os.waitpid, pid, 0)[1]


# internal stuff, do not look!

def _eintr_wrapper(f, *args):
    "Wraps some callable with a loop that retries on EINTR"
    while True:
        try:
            return f(*args)
        except OSError, e:
            if e.errno == errno.EINTR:
                continue
            else:
                raise

try:
    MAXFD = os.sysconf("SC_OPEN_MAX")
except:
    MAXFD = 256

# Used to print extra info in nested exceptions
def _custom_hook(t, v, tb):
    if hasattr(v, "child_traceback"):
        sys.stderr.write("Nested exception, original traceback " +
                "(most recent call last):\n")
        sys.stderr.write(v.child_traceback + ("-" * 70) + "\n")
    sys.__excepthook__(t, v, tb)

# XXX: somebody kill me, I deserve it :)
sys.excepthook = _custom_hook

