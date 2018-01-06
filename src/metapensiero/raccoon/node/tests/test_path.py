# -*- coding: utf-8 -*-
# :Project:   metapensiero.raccoon.node -- path tests
# :Created:   mer 17 feb 2016 02:18:24 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: © 2016, 2017, 2018 Alberto Berti
#

import pytest

from metapensiero.raccoon.node.path import Path


@pytest.fixture
def apath():
    return Path(
        ('foo', 'bar', 'a_session_id', 'server', 'node1', 'node2'),
        ('foo', 'bar', 'a_session_id'),
    )


def test_absolute_returns_absolute(apath):
    path = apath.resolve(('a', 'completely', 'different', 'address'))
    assert str(path) == 'a.completely.different.address'
    path = apath.resolve('a.completely.different.address')
    assert str(path) == 'a.completely.different.address'


def test_relative(apath):
    path = apath.resolve('@client.node1.node2')
    assert str(path) == 'foo.bar.a_session_id.client.node1.node2'
    path = apath.resolve(('@client', 'node1', 'node2'))
    assert str(path) == 'foo.bar.a_session_id.client.node1.node2'
