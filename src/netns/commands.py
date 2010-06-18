#!/usr/bin/env python
# vim:ts=4:sw=4:et:ai:sts=4

"""Utility functions to interact with system commands, such as `ip' and
`tc'."""

def get_interfaces(iface = None):
    """Returns a dictionary, indexed by interface number, with link and address
    information about each interface contained in another dict.

    ret = {
        1: {
            'name'   : 'lo',
            'flags'  : ['UP', 'LOOPBACK'],
            'mtu'    : 16436,
            'qdisc'  : 'noqueue',
            'lladdr' : '00:00:00:00:00:00',
            'addr'   : [ {
                'addr'  : '127.0.0.1',
                'plen'  : 8,
                'bcast' : None,
                'family': 'inet'
            }, {
                'addr'  : '::1',
                'plen'  : 128,
                'family': 'inet6'
            } ]
        },
    }"""
    pass

def get_routes():
    pass
