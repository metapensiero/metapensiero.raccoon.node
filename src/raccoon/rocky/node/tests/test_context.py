# -*- coding: utf-8 -*-
# :Project:   metapensiero.raccoon.node -- context class tests
# :Created:   mar 16 feb 2016 18:33:36 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: © 2016, 2017, 2018 Alberto Berti
#

import pytest
from raccoon.rocky.node import NodeContext, Registry


def test_attribute_accessing():

    nc = NodeContext(loop=4, path_resolvers=[1, 2])

    assert nc.path_resolvers == [1, 2]
    assert nc.loop == 4
    assert isinstance(nc.registry, Registry)

def test_standard_sub_instance():

    nc = NodeContext(loop=4, path_resolvers=[1, 2])

    nc2 = nc.new(loop=6)
    nc2.path_resolvers == [1, 2]
    assert nc2.loop == 6
    assert nc2.registry is nc.registry
    with pytest.raises(AttributeError):
        nc2.pollo

    assert isinstance(nc2, NodeContext)
