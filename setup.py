#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ts=4:sw=4:et:ai:sts=4

from distutils.core import setup, Extension, Command

setup(
        name        = 'nemu',
        version     = '0.3',
        description = 'A lightweight network emulator embedded in a small '
                      'python library.',
        author      = 'Martín Ferrari, Alina Quereilhac',
        author_email = 'martin.ferrari@gmail.com, aquereilhac@gmail.com',
        url         = 'http://code.google.com/p/nemu/',
        license     = 'GPLv2',
        platforms   = 'Linux',
        packages    = ['nemu'],
        package_dir = {'': 'src'}
        )
