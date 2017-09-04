#!/usr/bin/env python2
# -*- coding: utf-8 -*-
# vim: ts=4:sw=4:et:ai:sts=4

from distutils.core import setup, Extension, Command

setup(
        name        = 'nemu',
        version     = '0.3.1',
        description = 'A lightweight network emulator embedded in a small '
                      'python library.',
        author      = 'Martín Ferrari, Alina Quereilhac',
        author_email = 'martin.ferrari@gmail.com, aquereilhac@gmail.com',
        url         = 'https://github.com/TheTincho/nemu',
        license     = 'GPLv2',
        platforms   = 'Linux',
        packages    = ['nemu'],
        install_requires = ['python-unshare', 'python-passfd'],
        package_dir = {'': 'src'}
        )
