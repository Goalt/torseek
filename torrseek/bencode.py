"""Minimal bencode encoder/decoder (BEP 3)."""
from __future__ import annotations


def encode(obj) -> bytes:
    out: list[bytes] = []
    _enc(obj, out)
    return b"".join(out)


def _enc(obj, out: list[bytes]) -> None:
    if isinstance(obj, bool):
        raise TypeError("bool is not bencodable")
    if isinstance(obj, int):
        out.append(b"i%de" % obj)
    elif isinstance(obj, (bytes, bytearray)):
        out.append(b"%d:" % len(obj))
        out.append(bytes(obj))
    elif isinstance(obj, str):
        _enc(obj.encode("utf-8"), out)
    elif isinstance(obj, (list, tuple)):
        out.append(b"l")
        for x in obj:
            _enc(x, out)
        out.append(b"e")
    elif isinstance(obj, dict):
        out.append(b"d")
        items = [(k.encode("utf-8") if isinstance(k, str) else k, v) for k, v in obj.items()]
        for k, v in sorted(items):
            _enc(k, out)
            _enc(v, out)
        out.append(b"e")
    else:
        raise TypeError(f"cannot bencode {type(obj).__name__}")


def decode(data: bytes):
    value, end = _dec(data, 0)
    if end != len(data):
        raise ValueError("trailing data after bencoded value")
    return value


def _dec(data: bytes, i: int):
    c = data[i:i + 1]
    if c == b"i":
        end = data.index(b"e", i)
        return int(data[i + 1:end]), end + 1
    if c == b"l":
        i += 1
        items = []
        while data[i:i + 1] != b"e":
            v, i = _dec(data, i)
            items.append(v)
        return items, i + 1
    if c == b"d":
        i += 1
        d = {}
        while data[i:i + 1] != b"e":
            k, i = _dec(data, i)
            v, i = _dec(data, i)
            d[k] = v
        return d, i + 1
    if c.isdigit():
        colon = data.index(b":", i)
        n = int(data[i:colon])
        start = colon + 1
        if start + n > len(data):
            raise ValueError("truncated string")
        return data[start:start + n], start + n
    raise ValueError(f"bad bencode at offset {i}")


def info_span(data: bytes) -> tuple[int, int]:
    """Byte range of the raw 'info' value inside a .torrent (for the infohash)."""
    if data[:1] != b"d":
        raise ValueError("not a dict")
    i = 1
    while data[i:i + 1] != b"e":
        k, i = _dec(data, i)
        start = i
        _, i = _dec(data, i)
        if k == b"info":
            return start, i
    raise ValueError("no info dict")
