#!/usr/bin/env python
# Copyright 2014-2015 Canonical Limited.
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


import unittest
import mock

from jujubigdata import relations


class TestSpecMatchingRelation(unittest.TestCase):
    def setUp(self):
        self.data = None
        self.cache = {}
        self.relation = relations.SpecMatchingRelation(
            spec={'field': 'valid'},
            relation_name='test',
            required_keys=['foo'],
            datastore=mock.MagicMock(),
            cache=self.cache)
        self.relation.unfiltered_data = lambda: self.data

    def test_ready(self):
        self.data = {'unit/0': {'spec': '{"field": "valid"}', 'foo': 'bar'}}
        self.assertTrue(self.relation.is_ready())

    def test_not_ready(self):
        self.data = {}
        self.assertFalse(self.relation.is_ready())
        self.cache.clear()
        self.data = {'unit/0': {}}
        self.assertFalse(self.relation.is_ready())
        self.cache.clear()
        self.data = {'unit/0': {'no-spec': '{"field": "valid"}', 'foo': 'bar'}}
        self.assertFalse(self.relation.is_ready())
        self.cache.clear()
        self.data = {'unit/0': {'spec': '{"field": "valid"}', 'no-foo': 'bar'}}
        self.assertFalse(self.relation.is_ready())
        self.cache.clear()
        self.data = {'unit/0': {'spec': '{"field": "invalid"}', 'no-foo': 'bar'}}
        self.assertFalse(self.relation.is_ready())

    def test_invalid(self):
        self.data = {'unit/0': {'spec': '{"field": "invalid"}', 'foo': 'bar'}}
        self.assertRaises(ValueError, self.relation.is_ready)


if __name__ == '__main__':
    unittest.main()
