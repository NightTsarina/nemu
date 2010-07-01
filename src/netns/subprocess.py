#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import fcntl, grp, os, pickle, pwd, signal, sys, traceback

def spawn(executable, argv = None, cwd = None, env = None,
        stdin = None, stdout = None, stderr = None, user = None):
    """Forks and execs a program, with stdio redirection and user switching.
    The program is specified by `executable', if it does not contain any slash,
    the PATH environment variable is used to search for the file.

    The `user` parameter, if not None, specifies a user name to run the
    command as, after setting its primary and secondary groups. If a numerical
    UID is given, a reverse lookup is performed to find the user name and
    then set correctly the groups.

    To run the program in a different directory than the current one, it should
    be set in `cwd'.

    If specified, `env' replaces the caller's environment with the dictionary
    provided.

    The standard input, output, and error of the created process will be
    redirected to the file descriptors specified by `stdin`, `stdout`, and
    `stderr`, respectively. These parameters must be integers or None, in which
    case, no redirection will occur. If the value is negative, the respective
    file descriptor is closed in the executed program.

    Note that the original descriptors are not closed, and that piping should
    be handled externally.
    
    Exceptions occurred while trying to set up the environment or executing the
    program are propagated to the parent."""

    userfd = [stdin, stdout, stderr]
    filtered_userfd = filter(lambda x: x != None and x >= 0, userfd)
    sysfd = [x.fileno() for x in sys.stdin, sys.stdout, sys.stderr]
    # Verify there is no clash
    assert not (set(sysfd) & set(filtered_userfd))

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
                    os.dup2(userfd[i], sysfd[i])
                    os.close(userfd[i]) # only in child!
                if userfd[i] != None and userfd[i] < 0:
                    os.close(sysfd[i])
            # Set up special control pipe
            os.close(r)
            fcntl.fcntl(w, fcntl.F_SETFD, fcntl.FD_CLOEXEC)
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
                os.write(w, pickle.dumps(v))
                os.close(w)
            except:
                traceback.print_exc()
            os._exit(1)

    os.close(w)

    # read EOF for success, or a string as error info
    s = ""
    while True:
        s1 = os.read(r, 4096)
        if s1 == "":
            break
        s += s1
    os.close(r)

    if s == "":
        return pid

    # It was an error
    os.waitpid(pid, 0)
    exc = pickle.loads(s)
    # XXX: sys.excepthook
    #print exc.child_traceback
    raise exc

# Used to print extra info in nested exceptions
def _custom_hook(t, v, tb):
    sys.stderr.write("wee\n")
    if hasattr(v, "child_traceback"):
        sys.stderr.write("Nested exception, original traceback " +
                "(most recent call last):\n")
        sys.stderr.write(v.child_traceback + ("-" * 70) + "\n")
    sys.__excepthook__(t, v, tb)

# XXX: somebody kill me, I deserve it :)
sys.excepthook = _custom_hook

def poll(pid):
    """Check if the process already died. Returns the exit code or None if
    the process is still alive."""
    r = os.waitpid(pid, os.WNOHANG)
    if r[0]:
        return r[1]
    return None

def wait(pid):
    """Wait for process to die and return the exit code."""
    return os.waitpid(pid, 0)[1]

class Subprocess(object):
    # FIXME: this is the visible interface; documentation should move here.
    """OO-style interface to spawn(), but invoked through the controlling
    process."""
    # FIXME
    default_user = None
    def __init__(self, node, executable, argv = None, cwd = None, env = None,
            stdin = None, stdout = None, stderr = None, user = None):
        self._slave = node._slave

        if user == None:
            user = Subprocess.default_user

        # confusingly enough, to go to the function at the top of this file,
        # I need to call it thru the communications protocol: remember that
        # happens in another process!
        self._pid = self._slave.spawn(executable, argv = argv, cwd = cwd,
                env = env, stdin = stdin, stdout = stdout, stderr = stderr,
                user = user)

        node._add_subprocess(self)

    @property
    def pid(self):
        return self._pid

    def poll(self):
        r = self._slave.poll(self._pid)
        if r != None:
            del self._pid
            self.return_value = r
        return r

    def wait(self):
        r = self._slave.wait(self._pid)
        del self._pid
        self.return_value = r
        return r

    def signal(self, sig = signal.SIGTERM):
        return self._slave.signal(self._pid, sig)
