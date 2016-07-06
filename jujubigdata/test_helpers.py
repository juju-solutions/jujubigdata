# Copyright 2016 Canonical Limited.
#
# This file is part of jujubigdata.
#
# jujubigdata is free software: you can redistribute it and/or modify
# it under the terms of the Apache License version 2.0.
#
# jujubigdata is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# Apache License for more details.


from path import Path
import mock
import os
import sys
import unittest


class BigtopHarness(unittest.TestCase):
    '''
    This class is a testing harness that aids in testing layered
    charms that have been built on top of the apache-bigtop-base
    layer. It is intended to be the parent class for relevant test
    classes.

    This class automatically mocks out some modules in the layers that
    apache-bigtop-base depends on. It also automatically provides a
    mock for hookenv.status_set, so that you can test out methods that
    act based upon status.

    '''
    modules_to_mock = [
        'charms.layer.apache_bigtop_base.layer',
        'apache_bigtop_base.hookenv'
    ]

    def setUp(self, add_modules=None):
        '''
        Mock out many things.

        @param list add_modules: pass in a list of additional modules
        to mock. Each item in the list should be a string indicating a
        module to mock out. The format of the string is the same as
        the string that you'd pass into mock.patch in the Python mock
        library.

        '''
        self.patchers = []
        self.mocks = {}

        modules_to_mock = self.modules_to_mock + (add_modules or [])

        for module in modules_to_mock:
            patcher = mock.patch(module)
            self.mocks[module] = patcher.start()
            self.patchers.append(patcher)

        # Setup status list
        self.statuses = []
        mock_status = self.mocks['apache_bigtop_base.hookenv']
        mock_status.status_set = lambda a, b: self.statuses.append((a,b))

    def tearDown(self):
        for patcher in self.patchers:
            patcher.stop()

    @property
    def last_status(self):
        '''Helper for mocked out status list.'''

        return self.statuses[-1]

    @classmethod
    def tearDownClass(cls):
        '''
        We don't mock out some calls that write to the unit state
        db. Clean up that file here.

        '''
        cwd = os.getcwd()
        state_db = Path(cwd) / '.unit-state.db'
        if state_db.exists():
            state_db.remove()
