# vim:ts=4:sw=4:et:ai:sts=4
# -*- coding: utf-8 -*-

# Copyright 2010, 2011 INRIA
# Copyright 2011 Martín Ferrari <martin.ferrari@gmail.com>
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

import errno, os, os.path, socket, subprocess, sys, syslog
from syslog import LOG_ERR, LOG_WARNING, LOG_NOTICE, LOG_INFO, LOG_DEBUG


__all__ = ["IP_PATH", "TC_PATH", "BRCTL_PATH", "SYSCTL_PATH", "HZ"]
__all__ += ["TCPDUMP_PATH", "NETPERF_PATH", "XAUTH_PATH", "XDPYINFO_PATH"]
__all__ += ["execute", "backticks", "eintr_wrapper"]
__all__ += ["find_listen_port"]
__all__ += ["LOG_ERR", "LOG_WARNING", "LOG_NOTICE", "LOG_INFO", "LOG_DEBUG"]
__all__ += ["set_log_level", "logger"]
__all__ += ["error", "warning", "notice", "info", "debug"]


def find_bin(name, extra_path = None):
    """Try hard to find the location of needed programs."""
    search = []
    if "PATH" in os.environ:
        search += os.environ["PATH"].split(":")
    search.extend(os.path.join(x, y)
            for x in ("/", "/usr/", "/usr/local/")
            for y in ("bin", "sbin"))
    if extra_path:
        search += extra_path

    for dirr in search:
        path = os.path.join(dirr, name)
        if os.path.exists(path):
            return path
    return None

def find_bin_or_die(name, extra_path = None):
    """Try hard to find the location of needed programs; raise on failure."""
    res = find_bin(name, extra_path)
    if not res:
        raise RuntimeError("Cannot find `%s', impossible to continue." % name)
    return res

IP_PATH     = find_bin_or_die("ip")
TC_PATH     = find_bin_or_die("tc")
BRCTL_PATH  = find_bin_or_die("brctl")
SYSCTL_PATH = find_bin_or_die("sysctl")

# Optional tools
TCPDUMP_PATH = find_bin("tcpdump")
NETPERF_PATH = find_bin("netperf")
XAUTH_PATH = find_bin("xauth")
XDPYINFO_PATH = find_bin("xdpyinfo")

# Seems this is completely bogus. At least, we can assume that the internal HZ
# is bigger than this.
HZ = os.sysconf("SC_CLK_TCK")

try:
    os.stat("/sys/class/net")
except:
    raise RuntimeError("Sysfs does not seem to be mounted, impossible to " +
            "continue.")

def execute(cmd):
    """Execute a command, if the return value is non-zero, raise an exception.
    
    Raises:
        RuntimeError: the command was unsuccessful (return code != 0).
    """
    debug("execute(%s)" % cmd)
    null = open("/dev/null", "r+")
    proc = subprocess.Popen(cmd, stdout = null, stderr = subprocess.PIPE)
    _, err = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError("Error executing `%s': %s" % (" ".join(cmd), err))

def backticks(cmd):
    """Execute a command and capture its output.
    If the return value is non-zero, raise an exception.
   
    Returns:
        (stdout, stderr): tuple containing the captured output.
    Raises:
        RuntimeError: the command was unsuccessful (return code != 0).
    """
    debug("backticks(%s)" % cmd)
    proc = subprocess.Popen(cmd, stdout = subprocess.PIPE,
            stderr = subprocess.PIPE)
    out, err = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError("Error executing `%s': %s" % (" ".join(cmd), err))
    return out

def eintr_wrapper(func, *args):
    "Wraps some callable with a loop that retries on EINTR."
    while True:
        try:
            return func(*args)
        except OSError, ex: # pragma: no cover
            if ex.errno == errno.EINTR:
                continue
            raise
        except IOError, ex: # pragma: no cover
            if ex.errno == errno.EINTR:
                continue
            raise

def find_listen_port(family = socket.AF_INET, type = socket.SOCK_STREAM,
        proto = 0, addr = "127.0.0.1", min_port = 1, max_port = 65535):
    sock = socket.socket(family, type, proto)
    for port in range(min_port, max_port + 1):
        try:
            sock.bind((addr, port))
            return sock, port
        except socket.error:
            pass
    raise RuntimeError("Cannot find an usable port in the range specified")

# Logging
_log_level = LOG_WARNING
_log_use_syslog = False
_log_stream = sys.stderr
_log_syslog_opts = ()
_log_pid = os.getpid()

def set_log_level(level):
    "Sets the log level for console messages, does not affect syslog logging."
    global _log_level
    assert level > LOG_ERR and level <= LOG_DEBUG
    _log_level = level

def set_log_output(stream):
    "Redirect console messages to the provided stream."
    global _log_stream
    assert hasattr(stream, "write") and hasattr(stream, "flush")
    _log_stream = stream

def log_use_syslog(use = True, ident = None, logopt = 0,
        facility = syslog.LOG_USER):
    "Enable or disable the use of syslog for logging messages."
    global _log_use_syslog, _log_syslog_opts
    _log_syslog_opts = (ident, logopt, facility)
    _log_use_syslog = use
    _init_log()

def _init_log():
    if not _log_use_syslog:
        syslog.closelog()
        return
    (ident, logopt, facility) = _log_syslog_opts 
    if not ident:
        #ident = os.path.basename(sys.argv[0])
        ident = "nemu"
    syslog.openlog("%s[%d]" % (ident, os.getpid()), logopt, facility)
    info("Syslog logging started")

def logger(priority, message):
    "Print a log message in syslog, console or both."
    if _log_use_syslog:
        if os.getpid() != _log_pid:
            _init_log()  # Need to tell syslog the new PID.
        syslog.syslog(priority, message)
        return
    if priority > _log_level:
        return

    eintr_wrapper(_log_stream.write,
            "[%d] %s\n" % (os.getpid(), message.rstrip()))
    _log_stream.flush()

def error(message):
    logger(LOG_ERR, message)
def warning(message):
    logger(LOG_WARNING, message)
def notice(message):
    logger(LOG_NOTICE, message)
def info(message):
    logger(LOG_INFO, message)
def debug(message):
    logger(LOG_DEBUG, message)

def _custom_hook(tipe, value, traceback): # pragma: no cover
    """Custom exception hook, to print nested exceptions information."""
    if hasattr(value, "child_traceback"):
        sys.stderr.write("Nested exception, original traceback " +
                "(most recent call last):\n")
        sys.stderr.write(value.child_traceback + ("-" * 70) + "\n")
    sys.__excepthook__(tipe, value, traceback)

sys.excepthook = _custom_hook

