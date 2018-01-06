# -*- coding: utf-8 -*-
# :Project:   metapensiero.raccoon.node -- A base object for publishing WAMP resources
# :Created:   dom 09 ago 2015 12:57:35 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: © 2016, 2017, 2018 Alberto Berti
#

import logging


NOISY_ERROR_LOGGER = logging.Logger.error


def log_noisy_error(logger, *args, **kwargs):
    NOISY_ERROR_LOGGER(logger, *args, **kwargs)

from .path import Path
from .context import NodeContext, WAMPNodeContext
from .node import Node, WAMPNode
from .wamp import call

from . import serialize


__all__ = (
    'Node',
    'NodeContext',
    'Path',
    'WAMPNode',
    'WAMPNodeContext',
    'call',
    'serialize',
)
