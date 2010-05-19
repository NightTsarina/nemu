#!/usr/bin/env python
# vim: set fileencoding=utf-8
# vim: ts=4:sw=4:et:ai:sts=4
from distutils.core import setup, Extension, Command

setup(
        name        = 'netns',
        version     = '0.1',
        description = 'foo',
#        long_description = longdesc,
        author      = 'Martin Ferrari',
        author_email = 'martin.ferrari@gmail.com',
#        url         = 'http://code.google.com/p/python-unshare/',
        license     = 'GPLv2',
        platforms   = 'Linux',
        packages    = ['netns'],
        package_dir = {'': 'src'}
        )
