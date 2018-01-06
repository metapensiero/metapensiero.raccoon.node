# -*- coding: utf-8 -*-
# :Project:   metapensiero.raccoon.node -- exceptions
# :Created:   mer 18 ott 2017 19:51:50 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright © 2016, 2017, 2018 Alberto Berti
#


class DispatchError(Exception):
    """Exception raised during dispatch."""


class NodeError(Exception):
    """Error raised during node add/remove operations."""


class RPCError(Exception):
    "Exception raised when an RPC cannot be performed."