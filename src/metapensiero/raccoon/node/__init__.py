# -*- coding: utf-8 -*-
# :Project:   metapensiero.raccoon.node -- A base object for publishing WAMP resources
# :Created:   dom 09 ago 2015 12:57:35 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: © 2016, 2017, 2018 Alberto Berti
#

from metapensiero.signal import handler, MultipleResults, NoResult, Signal


SPEC_CONTAINER_MEMBER_NAME = '_publish'
"Special attribute name to attach rocky specific info to decorated methods."


from .context import NodeContext
from .deco import call
from .dispatch import Dispatcher
from .node import Node
from .path import Path
from .registry import Registry
from .signal import NodeInitMeta

from . import serialize


__all__ = (
    'Dispatcher',
    'MultipleResults',
    'Node',
    'NodeContext',
    'NodeInitMeta',
    'NoResult',
    'Path',
    'Registry',
    'Signal',
    'call',
    'handler',
    'serialize',
)
