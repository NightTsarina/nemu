#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

import re
import subprocess

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
                    'idx':      match.group(1),
                    'flags':    match.group(3).split(","),
                    'mtu':      match.group(4),
                    'qdisc':    match.group(5),
                    'addr':     []
                    }
            out[cur]['up'] = 'UP' in out[cur]['flags']
            continue
        # Assume cur is defined
        assert cur != None
        match = re.search(r'^\s+link/\S* ([0-9a-f:]+)(?: |$)', line)
        if match != None:
            out[cur]['lladdr'] = match.group(1)
            continue

        match = re.search(r'^\s+inet ([0-9.]+)/(\d+)(?: brd ([0-9.]+))?', line)
        if match != None:
            out[cur]['addr'].append({
                'addr': match.group(1),
                'plen': int(match.group(2)),
                'bcast': match.group(3),
                'family': 'inet'})
            continue

        match = re.search(r'^\s+inet6 ([0-9a-f:]+)/(\d+)(?: |$)', line)
        if match != None:
            out[cur]['addr'].append({
                'addr': match.group(1),
                'plen': int(match.group(2)),
                'family': 'inet6'})
            continue

        match = re.search(r'^\s{6}', line)
        assert match != None
    return out

def get_devs():
    ipcmd = subprocess.Popen(["ip", "addr", "list"],
            stdout = subprocess.PIPE)
    (outdata, errdata) = ipcmd.communicate()
    ipcmd.wait()
    return process_ipcmd(outdata)

def get_devs_netns(node):
    (outdata, errdata) = node.run_process(["ip", "addr", "list"])
    return process_ipcmd(outdata)


