# vim:ts=4:sw=4:et:ai:sts=4
import errno, os, os.path, socket, subprocess, sys, syslog
from syslog import LOG_ERR, LOG_WARNING, LOG_NOTICE, LOG_INFO, LOG_DEBUG

__all__ = ["ip_path", "tc_path", "brctl_path", "sysctl_path", "hz"]
__all__ += ["tcpdump_path", "netperf_path", "xauth_path", "xdpyinfo_path"]
__all__ += ["execute", "backticks", "eintr_wrapper"]
__all__ += ["find_listen_port"]
__all__ += ["LOG_ERR", "LOG_WARNING", "LOG_NOTICE", "LOG_INFO", "LOG_DEBUG"]
__all__ += ["set_log_level", "logger"]
__all__ += ["error", "warning", "notice", "info", "debug"]

def find_bin(name, extra_path = None):
    search = []
    if "PATH" in os.environ:
        search += os.environ["PATH"].split(":")
    for pref in ("/", "/usr/", "/usr/local/"):
        for d in ("bin", "sbin"):
            search.append(pref + d)
    if extra_path:
        search += extra_path

    for d in search:
            try:
                os.stat(d + "/" + name)
                return d + "/" + name
            except OSError, e:
                if e.errno != os.errno.ENOENT:
                    raise
    return None

def find_bin_or_die(name, extra_path = None):
    r = find_bin(name)
    if not r:
        raise RuntimeError(("Cannot find `%s' command, impossible to " +
                "continue.") % name)
    return r

ip_path     = find_bin_or_die("ip")
tc_path     = find_bin_or_die("tc")
brctl_path  = find_bin_or_die("brctl")
sysctl_path = find_bin_or_die("sysctl")

# Optional tools
tcpdump_path = find_bin("tcpdump")
netperf_path = find_bin("netperf")
xauth_path = find_bin("xauth")
xdpyinfo_path = find_bin("xdpyinfo")

# Seems this is completely bogus. At least, we can assume that the internal HZ
# is bigger than this.
hz = os.sysconf("SC_CLK_TCK")

try:
    os.stat("/sys/class/net")
except:
    raise RuntimeError("Sysfs does not seem to be mounted, impossible to " +
            "continue.")

def execute(cmd):
    debug("execute(%s)" % cmd)
    null = open("/dev/null", "r+")
    p = subprocess.Popen(cmd, stdout = null, stderr = subprocess.PIPE)
    out, err = p.communicate()
    if p.returncode != 0:
        raise RuntimeError("Error executing `%s': %s" % (" ".join(cmd), err))

def backticks(cmd):
    debug("backticks(%s)" % cmd)
    p = subprocess.Popen(cmd, stdout = subprocess.PIPE,
            stderr = subprocess.PIPE)
    out, err = p.communicate()
    if p.returncode != 0:
        raise RuntimeError("Error executing `%s': %s" % (" ".join(cmd), err))
    return out

def eintr_wrapper(f, *args):
    "Wraps some callable with a loop that retries on EINTR."
    while True:
        try:
            return f(*args)
        except OSError, e: # pragma: no cover
            if e.errno == errno.EINTR:
                continue
            raise
        except IOError, e: # pragma: no cover
            if e.errno == errno.EINTR:
                continue
            raise

def find_listen_port(family = socket.AF_INET, type = socket.SOCK_STREAM,
        proto = 0, addr = "127.0.0.1", min_port = 1, max_port = 65535):
    s = socket.socket(family, type, proto)
    for p in range(min_port, max_port + 1):
        try:
            s.bind((addr, p))
            return s, p
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

def set_log_output(file):
    "Redirect console messages to the provided stream."
    global _log_stream
    assert hasattr(file, "write") and hasattr(file, "flush")
    _log_stream = file

def log_use_syslog(use = True, ident = None, logopt = 0,
        facility = syslog.LOG_USER):
    "Enable or disable the use of syslog for logging messages."
    global _log_use_syslog, _log_syslog_opts
    if not use:
        if _log_use_syslog:
            syslog.closelog()
        _log_use_syslog = False
        return
    if not ident:
        #ident = os.path.basename(sys.argv[0])
        ident = "netns"
    syslog.openlog("%s[%d]" % (ident, os.getpid()), logopt, facility)
    _log_syslog_opts = (ident, logopt, facility)
    _log_use_syslog = True
    info("Syslog logging started")

def logger(priority, message):
    "Print a log message in syslog, console or both."
    global _log_use_syslog, _log_stream
    if _log_use_syslog:
        if os.getpid() != _log_pid:
            # Re-init logging
            log_use_syslog(_log_use_syslog, *_log_syslog_opts)
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

# Used to print extra info in nested exceptions
def _custom_hook(t, v, tb): # pragma: no cover
    if hasattr(v, "child_traceback"):
        sys.stderr.write("Nested exception, original traceback " +
                "(most recent call last):\n")
        sys.stderr.write(v.child_traceback + ("-" * 70) + "\n")
    sys.__excepthook__(t, v, tb)

# XXX: somebody kill me, I deserve it :)
sys.excepthook = _custom_hook

