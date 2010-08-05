# vim:ts=4:sw=4:et:ai:sts=4

import os

__all__ = ["ip_path", "tc_path", "brctl_path", "hz"]

def _find_bin(name):
    for pref in ("/", "/usr/", "/usr/local/"):
        for d in ("bin/", "sbin/"):
            try:
                os.stat(pref + d + name)
                return pref + d + name
            except OSError, e:
                if e.errno != os.errno.ENOENT:
                    raise
    raise RuntimeError("Cannot find `%s' command, impossible to continue." %
            name)

ip_path = _find_bin("ip")
tc_path = _find_bin("tc")
brctl_path = _find_bin("brctl")
sysctl_path = _find_bin("sysctl")

# Seems this is completely bogus. At least, we can assume that the internal HZ
# is bigger than this.
hz = os.sysconf("SC_CLK_TCK")

try:
    os.stat("/sys/class/net")
except:
    raise RuntimeError("Sysfs does not seem to be mounted, impossible to " +
            "continue.")

