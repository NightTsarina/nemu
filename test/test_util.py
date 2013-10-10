#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import os, re, subprocess, sys
import nemu.subprocess_
from nemu.environ import *

def process_ipcmd(str):
    cur = None
    out = {}
    for line in str.split("\n"):
        if line == "":
            cur = None
            continue
        match = re.search(r'^(\d+): (\S+): <(\S+)> mtu (\d+) qdisc (\S+)',
                line)
        if match != None:
            cur = match.group(2)
            out[cur] = {
                    'idx':      int(match.group(1)),
                    'flags':    match.group(3).split(","),
                    'mtu':      int(match.group(4)),
                    'qdisc':    match.group(5),
                    'addr':     []
                    }
            out[cur]['up'] = 'UP' in out[cur]['flags']
            continue
        # Assume cur is defined
        assert cur != None
        match = re.search(r'^\s+link/\S*(?: ([0-9a-f:]+))?(?: |$)', line)
        if match != None:
            out[cur]['lladdr'] = match.group(1)
            continue

        match = re.search(r'^\s+inet ([0-9.]+)/(\d+)(?: brd ([0-9.]+))?', line)
        if match != None:
            out[cur]['addr'].append({
                'address': match.group(1),
                'prefix_len': int(match.group(2)),
                'broadcast': match.group(3),
                'family': 'inet'})
            continue

        match = re.search(r'^\s+inet6 ([0-9a-f:]+)/(\d+)(?: |$)', line)
        if match != None:
            out[cur]['addr'].append({
                'address': match.group(1),
                'prefix_len': int(match.group(2)),
                'family': 'inet6'})
            continue

        match = re.search(r'^\s{4}', line)
        assert match != None
    return out

def get_devs():
    outdata = backticks([IP_PATH, "addr", "list"])
    return process_ipcmd(outdata)

def get_devs_netns(node):
    out = nemu.subprocess_.backticks_raise(node, [IP_PATH, "addr", "list"])
    return process_ipcmd(out)

def make_linux_ver(string):
    match = re.match(r'(\d+)\.(\d+)(?:\.(\d+))?(.*)', string)
    version, patchlevel, sublevel, extraversion = match.groups()
    if not sublevel:
        sublevel = 0
    return (int(version) << 16) + (int(patchlevel) << 8) + int(sublevel)

def get_linux_ver():
    return make_linux_ver(os.uname()[2])

# Unittest from Python 2.6 doesn't have these decorators
def _bannerwrap(f, text):
    name = f.__name__
    def banner(*args, **kwargs):
        sys.stderr.write("*** WARNING: Skipping test %s: `%s'\n" %
                (name, text))
        return None
    return banner
def skip(text):
    return lambda f: _bannerwrap(f, text)
def skipUnless(cond, text):
    return (lambda f: _bannerwrap(f, text)) if not cond else lambda f: f
def skipIf(cond, text):
    return (lambda f: _bannerwrap(f, text)) if cond else lambda f: f
