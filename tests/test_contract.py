"""SearchClient contract: one suite for every adapter (see conftest.ADAPTERS).

Generic tests use BROAD_QUERY, which must return more than one page.
Tests marked `special` rely on the mock's special queries.
"""
import hashlib
from datetime import datetime

import pytest

from torrseek import bencode
from torrseek.api.base import ApiError, NetworkError, NotFound, RateLimited, SearchClient
from torrseek.models import FileEntry, SearchPage, Sort, TorrentDetails, TorrentItem

BROAD_QUERY = "e"


def all_items(client, query, **kw):
    first = client.search(query, **kw)
    items = list(first.items)
    for p in range(2, first.total_pages + 1):
        items += client.search(query, page=p, **kw).items
    return first, items


def test_implements_protocol(client):
    assert isinstance(client, SearchClient)


def test_search_page_shape(client):
    page = client.search(BROAD_QUERY)
    assert isinstance(page, SearchPage)
    assert page.page == 1
    assert page.total_pages >= 2, "BROAD_QUERY should give several pages"
    assert 0 < len(page.items) <= 20
    for t in page.items:
        assert isinstance(t, TorrentItem)
        assert t.id and isinstance(t.id, str)
        assert t.title
        assert isinstance(t.size_bytes, int) and t.size_bytes > 0
        assert isinstance(t.seeders, int) and t.seeders >= 0
        assert isinstance(t.leechers, int) and t.leechers >= 0
        assert isinstance(t.uploaded_at, datetime)


def test_pagination_is_consistent(client):
    first, items = all_items(client, BROAD_QUERY)
    ids = [t.id for t in items]
    assert len(ids) == len(set(ids)), "pages must not overlap"
    assert len(items) == first.total_found
    assert first.total_pages == -(-first.total_found // 20)


def test_page_past_the_end_is_empty(client):
    first = client.search(BROAD_QUERY)
    beyond = client.search(BROAD_QUERY, page=first.total_pages + 1)
    assert beyond.items == []


def test_case_insensitive_substring(client):
    a = client.search("UBUNTU")
    b = client.search("ubuntu")
    assert a.total_found == b.total_found > 0
    assert all("ubuntu" in t.title.lower() for t in a.items)


@pytest.mark.parametrize("sort,key", [
    (Sort.SEEDERS, lambda t: t.seeders),
    (Sort.SIZE, lambda t: t.size_bytes),
    (Sort.DATE, lambda t: t.uploaded_at),
])
def test_sort_descending_across_pages(client, sort, key):
    _, items = all_items(client, BROAD_QUERY, sort=sort)
    values = [key(t) for t in items]
    assert values == sorted(values, reverse=True)


def test_category_filter(client):
    _, items = all_items(client, BROAD_QUERY, category="linux")
    assert items and all(t.category == "linux" for t in items)


def test_details_match_item(client):
    item = client.search("sintel").items[0]
    d = client.details(item.id)
    assert isinstance(d, TorrentDetails)
    assert d.as_item() == item
    assert d.files and all(isinstance(f, FileEntry) for f in d.files)
    assert sum(f.size_bytes for f in d.files) == d.size_bytes
    assert len(d.infohash) == 40 and int(d.infohash, 16) >= 0
    assert d.magnet.startswith("magnet:?xt=urn:btih:" + d.infohash)


def test_download_torrent_is_valid_bencode(client):
    item = client.search("debian").items[0]
    d = client.details(item.id)
    data = client.download_torrent(item.id)
    meta = bencode.decode(data)
    info = meta[b"info"]
    assert info[b"name"]
    assert len(info[b"pieces"]) % 20 == 0
    lengths = [info[b"length"]] if b"length" in info else [f[b"length"] for f in info[b"files"]]
    assert sum(lengths) == d.size_bytes
    count = -(-d.size_bytes // info[b"piece length"])
    assert len(info[b"pieces"]) == 20 * count
    start, end = bencode.info_span(data)
    assert hashlib.sha1(data[start:end]).hexdigest() == d.infohash


def test_unknown_id_is_not_found(client):
    with pytest.raises(NotFound):
        client.details("does-not-exist")
    with pytest.raises(NotFound):
        client.download_torrent("does-not-exist")


def test_errors_share_a_base():
    for cls in (NotFound, RateLimited, NetworkError):
        assert issubclass(cls, ApiError)


# ------------------------------------------------------------ special queries
def test_special_error(client):
    with pytest.raises(ApiError) as e:
        client.search("__error__")
    assert not isinstance(e.value, (NotFound, RateLimited, NetworkError))


def test_special_ratelimit(client):
    with pytest.raises(RateLimited) as e:
        client.search("__ratelimit__")
    assert e.value.retry_after > 0


def test_special_empty(client):
    page = client.search("__empty__")
    assert page.items == [] and page.total_found == 0 and page.total_pages == 0


def test_special_network(client):
    with pytest.raises(NetworkError):
        client.search("__network__")


def test_every_fixture_is_consistent():
    """The 200-ish fixtures: unique ids, legal categories, infohash matches the .torrent."""
    from torrseek.api.mock import MockClient
    from torrseek.models import DEFAULT_CATEGORIES

    c = MockClient(delay=(0, 0))
    recs = c.records
    assert 180 <= len(recs) <= 260
    hashes = set()
    for tid, r in recs.items():
        assert r["category"] in DEFAULT_CATEGORIES
        data = c.download_torrent(tid)
        s, e = bencode.info_span(data)
        assert hashlib.sha1(data[s:e]).hexdigest() == r["infohash"]
        hashes.add(r["infohash"])
    assert len(hashes) == len(recs)
