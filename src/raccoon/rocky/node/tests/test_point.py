from metapensiero.raccoon.node.registry.point import OwnerKey, EndPoint


def test_key_hashing():

    class AnotherPointKey(OwnerKey):
        pass

    class SecondPointKey(AnotherPointKey):
        _added_fields = 'foo'

    assert AnotherPointKey._fields == ('owner',)

    o = object()
    p = OwnerKey(o)
    ap = AnotherPointKey(o)

    assert isinstance(ap, OwnerKey)
    assert not isinstance(p, AnotherPointKey)

    oo = object()
    d = {p: oo}

    assert p == ap
    assert ap in d
    assert d[ap] == oo

    sp = SecondPointKey(o, oo)

    assert p != sp
    assert ap != sp
    assert (o, oo) == sp


def test_key_member_access():

    class AnotherPointKey(OwnerKey):
        pass

    class SecondPointKey(AnotherPointKey):
        _added_fields = 'foo'

    o, oo = object(), object()
    p = OwnerKey(o)
    ap = AnotherPointKey(o)
    sp = SecondPointKey(o, oo)

    assert p.owner is o
    assert ap.owner is o
    assert sp.foo is oo


def test_point_creation():

    class APointKey(OwnerKey):
        pass

    class AnRPCPoint(EndPoint):
        KEY_CLS = APointKey


    k = APointKey('bla')
    p = k.point()


    assert isinstance(p, AnRPCPoint)

    k2 = APointKey('bla')
    p2 = k2.point()

    assert isinstance(p, AnRPCPoint)
    assert p is p2
