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


import os
import tempfile
import unittest
import mock
from path import Path

from jujubigdata import utils


class TestError(RuntimeError):
    pass


class TestUtils(unittest.TestCase):
    def test_disable_firewall(self):
        with mock.patch.object(utils, 'check_call') as check_call:
            with utils.disable_firewall():
                check_call.assert_called_once_with(['ufw', 'disable'])
            check_call.assert_called_with(['ufw', 'enable'])

    def test_disable_firewall_on_error(self):
        with mock.patch.object(utils, 'check_call') as check_call:
            try:
                with utils.disable_firewall():
                    check_call.assert_called_once_with(['ufw', 'disable'])
                    raise TestError()
            except TestError:
                check_call.assert_called_with(['ufw', 'enable'])

    def test_re_edit_in_place(self):
        fd, filename = tempfile.mkstemp()
        os.close(fd)
        tmp_file = Path(filename)
        try:
            tmp_file.write_text('foo\nbar\nqux')
            utils.re_edit_in_place(tmp_file, {
                r'oo$': 'OO',
                r'a': 'A',
                r'^qux$': 'QUX',
            })
            self.assertEqual(tmp_file.text(), 'fOO\nbAr\nQUX')
        finally:
            tmp_file.remove()

    def test_xmlpropmap_edit_in_place(self):
        fd, filename = tempfile.mkstemp()
        os.close(fd)
        tmp_file = Path(filename)
        try:
            tmp_file.write_text(
                '<?xml version="1.0"?>\n'
                '<?xml-stylesheet type="text/xsl" href="configuration.xsl"?>\n'
                '\n'
                '<!-- Put site-specific property overrides in this file. -->\n'
                '\n'
                '<configuration>\n'
                '   <property>\n'
                '       <name>modify.me</name>\n'
                '       <value>1</value>\n'
                '       <description>Property to be modified</description>\n'
                '   </property>\n'
                '   <property>\n'
                '       <name>delete.me</name>\n'
                '       <value>None</value>\n'
                '       <description>Property to be removed</description>\n'
                '   </property>\n'
                '   <property>\n'
                '       <name>do.not.modify.me</name>\n'
                '       <value>0</value>\n'
                '       <description>Property to *not* be modified</description>\n'
                '   </property>\n'
                '</configuration>')
            with utils.xmlpropmap_edit_in_place(tmp_file) as props:
                del props['delete.me']
                props['modify.me'] = 'one'
                props['add.me'] = 'NEW'
            self.assertEqual(
                tmp_file.text(),
                '<?xml version="1.0" ?>\n'
                '<configuration>\n'
                '    <property>\n'
                '        <name>modify.me</name>\n'
                '        <value>one</value>\n'
                '        <description>Property to be modified</description>\n'
                '    </property>\n'
                '    <property>\n'
                '        <name>do.not.modify.me</name>\n'
                '        <value>0</value>\n'
                '        <description>Property to *not* be modified</description>\n'
                '    </property>\n'
                '    <property>\n'
                '        <name>add.me</name>\n'
                '        <value>NEW</value>\n'
                '    </property>\n'
                '</configuration>\n')
        finally:
            tmp_file.remove()


if __name__ == '__main__':
    unittest.main()
