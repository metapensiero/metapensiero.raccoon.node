# -*- coding: utf-8 -*-
# :Project:   metapensiero.raccoon.node -- exceptions
# :Created:   mer 18 ott 2017 19:51:50 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright © 2017, 2018 Alberto Berti
#


class InvocationError(Exception):
    """Exception raised during dispatch."""


class RPCError(Exception):
    "Exception raised when an RPC cannot be performed."
