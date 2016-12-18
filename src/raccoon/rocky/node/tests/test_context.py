# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- context class tests
# :Created:   mar 16 feb 2016 18:33:36 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016 Arstecnica s.r.l.
#

import pytest
from raccoon.rocky.node.context import WAMPNodeContext


def test_standard_instance():

    nc = WAMPNodeContext(wamp_session=1, wamp_details=2,
                         publication_wrapper=3, loop=4)

    assert nc.wamp_session == 1
    assert nc.wamp_details == 2
    assert nc.publication_wrapper == 3
    assert nc.loop == 4

def test_standard_sub_instance():

    nc = WAMPNodeContext(wamp_session=1, wamp_details=2,
                         publication_wrapper=3, loop=4)

    nc2 = nc.new(wamp_details=5, loop=6)
    assert nc2.wamp_session == 1
    assert nc2.wamp_details == 5
    assert nc2.publication_wrapper == 3
    assert nc2.loop == 6
    with pytest.raises(AttributeError):
        nc2.pollo

    assert isinstance(nc2, WAMPNodeContext)
