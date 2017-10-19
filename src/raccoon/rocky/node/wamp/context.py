# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- WAMP context
# :Created:   mer 18 ott 2017 19:51:50 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright © 2016, 2017 Arstecnica s.r.l.
#

from ..context import NodeContext


class WAMPNodeContext(NodeContext):
    """
    A :class:`~raccoon.rocky.node.node.Node` context with WAMP management
    details.
    """

    CONFIG_KEYS = NodeContext.CONFIG_KEYS + [
        'call_registration_options',
        'call_wrapper',
        'publication_wrapper',
        'subscription_registration_options',
        'subscription_wrapper',
        'wamp_details',
        'wamp_session',
    ]

    def __init__(self, loop=None, path_resolvers=None, wamp_session=None,
                 wamp_details=None, publication_wrapper=None,
                 subscription_wrapper=None, call_wrapper=None,
                 call_registration_options=None,
                 subscription_registration_options=None):
        super().__init__(loop=loop, path_resolvers=path_resolvers)
        self.wamp_session = wamp_session
        self.wamp_details = wamp_details
        self.publication_wrapper = publication_wrapper
        self.subscription_wrapper = subscription_wrapper
        self.call_wrapper = call_wrapper
        self.call_registration_options = call_registration_options
        self.subscription_registration_options = subscription_registration_options
