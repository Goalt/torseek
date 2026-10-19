"""Build .torrent files and magnet links from fixture records.

Pieces are synthetic (sha1 of a seed), so the files are structurally
valid torrents but do not point to real swarm data.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from urllib.parse import quote

from . import bencode

TRACKERS = (
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.demonii.com:1337/announce",
)


def piece_length_for(total: int) -> int:
    length = 256 * 1024
    while total / length > 1500:
        length *= 2
    return length


def build_info(record: dict) -> dict:
    files = record["files"]
    total = sum(f["size_bytes"] for f in files)
    plen = piece_length_for(total)
    count = max(1, -(-total // plen))
    seed = record["id"].encode()
    pieces = b"".join(hashlib.sha1(seed + b":%d" % i).digest() for i in range(count))
    info: dict = {"name": record["name"], "piece length": plen, "pieces": pieces}
    if len(files) == 1 and "/" not in files[0]["path"] and files[0]["path"] == record["name"]:
        info["length"] = files[0]["size_bytes"]
    else:
        info["files"] = [
            {"length": f["size_bytes"], "path": f["path"].split("/")} for f in files
        ]
    return info


def infohash(info: dict) -> str:
    return hashlib.sha1(bencode.encode(info)).hexdigest()


def build_torrent(record: dict) -> bytes:
    meta = {
        "announce": TRACKERS[0],
        "announce-list": [[t] for t in TRACKERS],
        "comment": record.get("description", "")[:200],
        "created by": "TorrSeek mock",
        "creation date": int(datetime.fromisoformat(record["uploaded_at"]).timestamp()),
        "info": build_info(record),
    }
    return bencode.encode(meta)


def magnet(infohash_hex: str, title: str) -> str:
    parts = [f"magnet:?xt=urn:btih:{infohash_hex}", "dn=" + quote(title, safe="")]
    parts += ["tr=" + quote(t, safe="") for t in TRACKERS]
    return "&".join(parts)
