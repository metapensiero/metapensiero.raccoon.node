# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- node serialization
# :Created:   dom 04 giu 2017 13:09:20 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: © 2017 Arstecnica s.r.l.
#

import abc
import sys

NODE_SERIALIZIED_ID_KEY = "__node_id__"
NODE_SERIALIZIED_VALUE_KEY = "__node_value__"
NODE_SERIALIZATION_CLASS_KEY = "_node_serialization_id"


class SerializationError(Exception):
    """Error raised during (De)Serialization."""


class Serializable(metaclass=abc.ABCMeta):
    """An abstract class which exposes the api that the class whose instances
    should be serialized should expose."""

    @abc.abstractmethod
    def node_serialize(self, instance, src_node=None):
        """Called by the node infrastructure to have the one instance of the
        class serialized.

        :param instance: An instance of the type to serialize
        :param src_node: the `Node` node that generated the `instance` that has
          to be serialized
        :returns: An instance of the `Serialized` class
        :raises SerializationError: if it's unable to serialize the instance
        """

    @abc.abstractmethod
    def node_deserialize(self, value, end_node=None):
        """Called by the node infrastructure to have a serialized state of an
        instance reconverted. I isn't enforced that the returned value is an
        instance of the managed class, it can be anything suitable.

        :param value: The serialized value, the value field of the
          containing Serialized instance.
        :param end_node: the `Node` instance to which the deserialized value
          will be submitted
        :returns: anything suitable to rephresent the serialized value.
        :raises SerializationError: if it's unable to deserialize the value

        """


class SerializedMeta(type):
    """Metaclass for the `Serialized` class, it is used to dynamically check
    if an instance of ``dict`` is also an instance of `Serialized`.
    """

    def __instancecheck__(self, instance):
        return (isinstance(instance, dict) and
                NODE_SERIALIZIED_ID_KEY in instance and
                NODE_SERIALIZIED_VALUE_KEY in instance and
                len(instance) == 2)

    "The ``serialization_id`` key name"
    id_key = NODE_SERIALIZIED_ID_KEY
    "The serialized value key name"
    value_key = NODE_SERIALIZIED_VALUE_KEY

    def get_id(cls, instance, default=None):
        """Given a ``dict`` which is also a `Serialized`, return the
        ``serialization_id`` contained."""
        return instance.get(cls.id_key, default)

    def get_value(cls, instance, default=None):
        """Given a ``dict`` which is also a `Serialized`, return the
        ``value`` contained."""
        return instance.get(cls.value_key, default)


class Serialized(dict, metaclass=SerializedMeta):
    """Rephresents a serialzed value. It is just a ``dict`` configured to have
    just a pair of entries, one for the ``serialization_id`` and the other for
    the serialized rephresentation. It dynamically checks if any instance of
    ``dict`` is a suitable instance of this class with normal
    ``isinstance(foo, Serialized)`` call.

    :param value: a serialized state. It must allow JSON serialization
    :param str serialization_id: a string identifying the serialized state,
      if not given the registry will fill it the registered id.
    """

    def __init__(self, value, serialization_id=None):
        super().__init__()
        self[NODE_SERIALIZIED_ID_KEY] = serialization_id
        self[NODE_SERIALIZIED_VALUE_KEY] = value


class SerializationDefinition:
    """Used to add an entry with serialization detail for the given class.
    It can be used as a class decorator.

    :param str serialization_id: a string identifying the serialized state
    :keyword bool allow_subclasses: if the current definition should be used
      also for subclasses of the given one. Defaults to ``False``
    :keyword serializer: an optional serialization class to be used.
    :keyword aliases: optional sequence of aliases of the ``serialization_id``
    """

    def __init__(self, serialization_id, *, allow_subclasses=False,
                 serializer=None, cls=None, aliases=None):
        self.serialization_id = serialization_id
        self.allow_subclasses = allow_subclasses
        self.serializer = serializer
        if aliases is None:
            aliases = ()
        else:
            aliases = tuple(aliases)
        self.aliases = aliases
        if cls:
            self.register_class(cls)
        else:
            cls = None

    def register_class(self, cls):
        """Register the given class in the registry, usable also as a class
        decorator.

        :param cls: the class to register
        :returns: the inputed ``cls``
        :raises SerializationError: if any configuration error is found
        """
        is_serializable = issubclass(cls, Serializable)
        if self.serializer is None:
            if is_serializable:
                self.serializer = cls
            else:
                raise SerializationError(f"No serializer provided and class"
                                         f" {cls.__name__} isn't serializable")
        else:
            if ((isinstance(self.serializer, type) and
                 issubclass(self.serializer, Serializable)) or
                (not isinstance(self.serializer, type) and
                 isinstance(self.serializer, Serializable))):
                Serializable.register(cls)
            else:
                raise SerializationError(f"The provided serializer is not "
                                         f"Serializable.")
        self.cls = cls
        if self.allow_subclasses:
            setattr(cls, NODE_SERIALIZATION_CLASS_KEY, self.serialization_id)
        REGISTRY.add_registration(self)
        return cls

    __call__ = register_class


class Registry:
    """A registry of serialization definitions indexed by *serialization_id*
    and *class*. An instance of this class is exported in place of the whole
    module for easier fruition."""

    SerializedMeta = SerializedMeta
    Serialized = Serialized
    Serializable = Serializable
    SerializationError = SerializationError
    SerializationDefinition = SerializationDefinition
    define = SerializationDefinition

    def __init__(self):
        self._id_to_definition = {}
        self._cls_to_definition = {}

    def add_registration(self, definition):
        """Add a definition to the registry. This is automatically called by
        each definition instance.

        :param definition: an instance of `SerializationDefinition`
        """
        assert (definition.serialization_id is not None and
                isinstance(definition.serialization_id, str))
        if (definition.serialization_id in self._id_to_definition or
            any(al in self._id_to_definition for al in definition.aliases)):
            raise SerializationError(f"The id '{definition.serialization_id}'"
                                     f" is taken already")
        assert definition.cls is not None
        if definition.cls in self._cls_to_definition:
            raise SerializationError(f"Class {definition.cls.__name__} is "
                                     f"already registered")

        for serial_id in ((definition.serialization_id,) + definition.aliases):
            self._id_to_definition[serial_id] = definition
        self._cls_to_definition[definition.cls] = definition

    def deserialize(self, serialized, end_node=None):
        """Called by node machinery to deserialize a value upon reception.

        :param serialized: an instance of `Serialized`
        :param end_node: the `Node` instance to which the deserialized value
          will be submitted
        :returns: anything suitable
        :raises SerializationError: if a matching definition cannot be found
        """
        if not isinstance(serialized, self.Serialized):
            raise SerializationError(f"{serialized!r} is not a valid "
                                     f"serialized value")
        definition = self._id_to_definition.get(
            serialized[NODE_SERIALIZIED_ID_KEY])
        if definition is None:
            raise SerializationError(f"Don't know how to deserialize "
                                     f"{serialized!r}")
        return definition.serializer.node_deserialize(
            serialized[NODE_SERIALIZIED_VALUE_KEY],
            end_node
        )

    def deserialize_args(self, args, kwargs, end_node=None):
        """Called to deserialize any `Serialized` value."""
        return (tuple((self.deserialize(v, end_node)
                       if isinstance(v, Serialized) else v)
                      for v in args),
                {k: (self.deserialize(v, end_node) if
                     isinstance(v, Serialized) else v)
                   for k, v in kwargs.items()})

    def deserialize_result(self, in_result, end_node=None):
        """Deserialize a scalar result or a tuple of results coming from
        :term:`WAMP` calls."""
        if isinstance(in_result, (tuple, list)):
            return type(in_result)(
                (self.deserialize(v, end_node)
                 if isinstance(v, Serialized) else v)
                for v in in_result)
        else:
            return (self.deserialize(in_result, end_node)
                    if isinstance(in_result, Serialized) else
                    in_result)

    def serialize(self, instance, src_node=None):
        """Called by node machinery to serialize an instance before sending it
        remotely.

        :param instance: an instance to serialize. Should be and instance of a
        :param src_node: the `Node` node that generated the `instance` that has
          to be serialized
          `Serializable` subclass
        :returns: an instance of `Serialized`
        :raises SerializationError: if a meatching serialization definition
          cannot be found
        """
        cls = type(instance)
        definition = None
        if cls in self._cls_to_definition:
            definition = self._cls_to_definition[cls]
        elif hasattr(instance, NODE_SERIALIZATION_CLASS_KEY):
            serialization_id = getattr(instance, NODE_SERIALIZATION_CLASS_KEY)
            if serialization_id in self._id_to_definition:
                definition = self._id_to_definition[serialization_id]
        if definition is None:
            raise SerializationError(f"Don't know how to serialize {instance!r}")
        result = definition.serializer.node_serialize(instance, src_node)
        if not isinstance(result, Serialized):
            result = Serialized(result)
        if Serialized.get_id(result) is None:
            result[NODE_SERIALIZIED_ID_KEY] = definition.serialization_id
        return result

    def serialize_args(self, args, kwargs, src_node=None):
        """Called to serialize any serializable value."""
        return (tuple((self.serialize(v, src_node) if
                       isinstance(v, Serializable) else v)
                      for v  in args),
                {k: (self.serialize(v, src_node) if
                     isinstance(v, Serializable) else v)
                   for k, v in kwargs.items()})

    def serialize_result(self, in_result, src_node=None):
        """Deserialize a scalar result or a tuple of results coming from
        :term:`WAMP` calls when """
        if isinstance(in_result, (tuple, list)):
            return type(in_result)(
                (self.serialize(v, src_node) if
                 isinstance(v, Serializable) else v)
                for v in in_result)
        else:
            return (self.serialize(in_result, src_node)
                    if isinstance(in_result, Serializable) else
                    in_result)


REGISTRY = Registry()

# from https://mail.python.org/pipermail/python-ideas/2012-May/014969.html
sys.modules[__name__] = REGISTRY
