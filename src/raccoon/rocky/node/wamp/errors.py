# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- exceptions
# :Created:   mer 18 ott 2017 19:51:50 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright © 2016, 2017 Arstecnica s.r.l.
#


class ProxyError(Exception):
    "Exception raised in `~.proxy.Proxy` code"


class RPCError(Exception):
    "Exception raised when an RPC cannot be performed."
