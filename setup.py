#!/usr/bin/env python
# vim: set fileencoding=utf-8
# vim: ts=4:sw=4:et:ai:sts=4
from distutils.core import setup, Extension, Command
import platform

# CHECK dependencies
# Linux kernel >= 2.6.36  
l = platform.uname()[2].split("-")[0].split(".")
l.reverse()
if sum( int(l[i])*pow(10,i) for i in xrange(len(l))) < 296:
    raise RuntimeError("Linux kernel >= 2.6.36 is required")

setup(
        name        = 'netns',
        version     = '0.1',
        description = '''A framework for creating emulated networks in a
        single host and run experiments on them''',
#        long_description = longdesc,
        author      = 'Martin Ferrari',
        author_email = 'martin.ferrari@gmail.com',
        url         = 'http://yans.pl.sophia.inria.fr/code/hgwebdir.cgi/netns/',
        license     = 'GPLv2',
        platforms   = 'Linux',
        packages    = ['netns'],
        package_dir = {'': 'src'}
        )
