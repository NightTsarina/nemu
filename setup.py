#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ts=4:sw=4:et:ai:sts=4

from distutils.core import setup, Extension, Command

setup(
        name        = 'nemu',
        version     = '0.1',
        description = '''A framework for creating emulated networks in a
        single host and run experiments on them''',
#        long_description = longdesc,
        author      = 'Martín Ferrari',
        author_email = 'martin.ferrari@gmail.com',
        url         = 'http://code.google.com/p/nemu/',
        license     = 'GPLv2',
        platforms   = 'Linux',
        packages    = ['nemu'],
        package_dir = {'': 'src'}
        )
