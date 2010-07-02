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
    `stderr`, respectively. These parameters must be open file objects,
    integers or None, in which case, no redirection will occur.

    Note that the original descriptors are not closed, and that piping should
    be handled externally.
    
    Exceptions occurred while trying to set up the environment or executing the
    program are propagated to the parent."""

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
        self._returncode = None

    @property
    def pid(self):
        return self._pid

    def poll(self):
        r = self._slave.poll(self._pid)
        if r != None:
            del self._pid
            self._returncode = r
        return self.returncode

    def wait(self):
        self._returncode = self._slave.wait(self._pid)
        del self._pid
        return self.returncode

    def signal(self, sig = signal.SIGTERM):
        return self._slave.signal(self._pid, sig)

    @property
    def returncode(self):
        if self._returncode == None:
            return None
        if os.WIFSIGNALED(self._returncode):
            return -os.WTERMSIG(self._returncode)
        if os.WIFEXITED(self._returncode):
            return os.EXITSTATUS(self._returncode)
        raise RuntimeError("Invalid return code")

    # FIXME: do we have any other way to deal with this than having explicit
    # destroy?
    def destroy(self):
        pass

PIPE = -1
STDOUT = -2
class Popen(Subprocess):
    def __init__(self, node, executable, argv = None, cwd = None, env = None,
            stdin = None, stdout = None, stderr = None, user = None,
            bufsize = 0):
        self.stdin = self.stdout = self.stderr = None
        fdmap = { "stdin": stdin, "stdout": stdout, "stderr": stderr }
        # if PIPE: all should be closed at the end
        for k, v in fdmap:
            if v == None:
                continue
            if v == PIPE:
                r, w = os.pipe()
                if k == "stdin":
                    setattr(self, k, os.fdopen(w, 'wb', bufsize))
                    fdmap[k] = r
                else:
                    setattr(self, k, os.fdopen(w, 'rb', bufsize))
                    fdmap[k] = w
            elif isinstance(v, int):
                pass
            else:
                fdmap[k] = v.fileno()
        if stderr == STDOUT:
            fdmap['stderr'] = fdmap['stdout']

        #print fdmap

        super(Popen, self).__init__(node, executable, argv = argv, cwd = cwd,
                env = env, stdin = fdmap['stdin'], stdout = fdmap['stdout'],
                stderr = fdmap['stderr'], user = user)

        # Close pipes, they have been dup()ed to the child
        for k, v in fdmap:
            if getattr(self, k) != None:
                _eintr_wrapper(os.close, v)

#    def comunicate(self, input = None)

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

# Used to print extra info in nested exceptions
def _custom_hook(t, v, tb):
    if hasattr(v, "child_traceback"):
        sys.stderr.write("Nested exception, original traceback " +
                "(most recent call last):\n")
        sys.stderr.write(v.child_traceback + ("-" * 70) + "\n")
    sys.__excepthook__(t, v, tb)

# XXX: somebody kill me, I deserve it :)
sys.excepthook = _custom_hook

