# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- utilities
# :Created:   mar 24 ott 2017 13:47:49 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright © 2017, 2018 Alberto Berti
#

import enum

@enum.unique
class RPCType(enum.Enum):
    """The possible types of registrations to external RPC services that the
    system is able to ask."""

    CALL = 1
    """The type for a procedure or any other callable that performs a certain
    operation on the submitted data and possibly returns a result.
    """
    EVENT = 2
    """The type for the subscription of a callable to a channel (or topic)."""
