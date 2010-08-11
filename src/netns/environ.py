# vim:ts=4:sw=4:et:ai:sts=4

import os, subprocess

__all__ = ["ip_path", "tc_path", "brctl_path", "sysctl_path", "hz"]
__all__ += ["tcpdump_path", "netperf_path"]
__all__ += ["execute", "backticks"]

def find_bin(name):
    search = []
    if "PATH" in os.environ:
        search += os.environ["PATH"].split(":")
    for pref in ("/", "/usr/", "/usr/local/"):
        for d in ("bin/", "sbin/"):
            search.append(pref + d)
    for d in search:
            try:
                os.stat(d + name)
                return d + name
            except OSError, e:
                if e.errno != os.errno.ENOENT:
                    raise
    return None

def find_bin_or_die(name):
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

# Seems this is completely bogus. At least, we can assume that the internal HZ
# is bigger than this.
hz = os.sysconf("SC_CLK_TCK")

try:
    os.stat("/sys/class/net")
except:
    raise RuntimeError("Sysfs does not seem to be mounted, impossible to " +
            "continue.")

def execute(cmd):
    #print " ".join(cmd)#; return
    null = open("/dev/null", "r+")
    p = subprocess.Popen(cmd, stdout = null, stderr = subprocess.PIPE)
    out, err = p.communicate()
    if p.returncode != 0:
        raise RuntimeError("Error executing `%s': %s" % (" ".join(cmd), err))

def backticks(cmd):
    p = subprocess.Popen(cmd, stdout = subprocess.PIPE,
            stderr = subprocess.PIPE)
    out, err = p.communicate()
    if p.returncode != 0:
        raise RuntimeError("Error executing `%s': %s" % (" ".join(cmd), err))
    return out

