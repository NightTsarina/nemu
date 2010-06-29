#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import fcntl, grp, os, pickle, pwd, signal, sys, traceback

class Popen(object):
    """Class that attempts to provide low-leven popen-like behaviour, with the
    extra feature of being able to switch user before executing the command."""
    def __init__(self, user, file, argv, cwd = None, env = None,
            stdin = None, stdout = None, stderr = None):
        """Check Python's subprocess.Popen for the intended behaviour. The
        extra `user` argument, if not None, specifies a username to run the
        command as, including its primary and secondary groups. If a numerical
        UID is given, a reverse lookup is performed to find the user name and
        then set correctly the groups.  Note that `stdin`, `stdout`, and
        `stderr` can only be integers representing file descriptors, and that
        they are not closed by this class; piping should be handled
        externally."""

        userfd = [stdin, stdout, stderr]
        sysfd = [x.fileno() for x in sys.stdin, sys.stdout, sys.stderr]
        # Verify there is no clash
        assert not (set(filter(None, userfd)) & set(filter(None, sysfd)))

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
                    if userfd[i] != None:
                        os.dup2(userfd[i], sysfd[i])
                        os.close(userfd[i])
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
                    argv = [ file ]
                if '/' in file: # Should not search in PATH
                    if env != None:
                        os.execve(file, argv, env)
                    else:
                        os.execv(file, argv)
                else: # use PATH
                    if env != None:
                        os.execvpe(file, argv, env)
                    else:
                        os.execvp(file, argv)
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
            self._pid = pid
            return

        # It was an error
        os.waitpid(pid, 0)
        raise pickle.loads(s)

    @property
    def pid(self):
        return self._pid

    def poll(self):
        """Check if the process already died. Returns the exit code or None if
        the process is still alive."""
        r = os.waitpid(self._pid, os.WNOHANG)
        if r[0]:
            del self._pid
            return r[1]
        return None

    def wait(self):
        """Wait for process to die and return the exit code."""
        r = os.waitpid(self._pid, 0)[1]
        del self._pid
        return r

    def kill(self, sig = signal.SIGTERM):
        """Kill the process with the specified signal. Note that the process
        still needs to be waited for to avoid zombies."""
        os.kill(self._pid, sig)
