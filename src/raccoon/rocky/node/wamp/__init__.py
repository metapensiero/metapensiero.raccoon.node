# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- WAMP compatibility subpackage
# :Created:   mer 18 ott 2017 19:51:50 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright © 2016, 2017 Arstecnica s.r.l.
#

import logging


NODE_INTERNAL_SIGNALS = (
    'on_node_bind',
    'on_node_register',
    'on_node_registration_success',
    'on_node_registration_failure',
    'on_node_add',
    'on_node_unbind',
    'on_node_unregister',
)

SPEC_CONTAINER_MEMBER_NAME = '_publish'
"Special attribute name to attach rocky specific info to decorated methods."

NOISY_ERROR_LOGGER = logging.Logger.error


def log_noisy_error(logger, *args, **kwargs):
    NOISY_ERROR_LOGGER(logger, *args, **kwargs)

from .abc import AbstractWAMPNode
from .context import WAMPNodeContext
from .deco import call
from .node import WAMPNode
from .proxy import Proxy
from .signal import WAMPInitMeta

__all__ = (
    'AbstractWAMPNode',
    'Proxy',
    'WAMPInitMeta',
    'WAMPNode',
    'WAMPNodeContext',
    'call'
)
