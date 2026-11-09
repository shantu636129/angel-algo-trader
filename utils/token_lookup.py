import json
import os

SCRIP_MASTER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "scrip_master.json"
)

_cache = None


def _load():
    global _cache
    if _cache is None:
        with open(SCRIP_MASTER_PATH, "r") as f:
            _cache = json.load(f)
    return _cache


def find_token(name=None, symbol=None, exch_seg=None, symbol_contains=None, limit=20):
    """
    Look up instrument tokens from the local scrip master cache.

    name: exact instrument 'name' field match, e.g. 'ZENTEC', 'SBIN', 'RELIANCE'
    symbol: exact instrument 'symbol' field match, e.g. 'ZENTEC-EQ', 'SBIN-EQ', 'RELIANCE-EQ'
    exch_seg: 'NSE', 'BSE', 'NFO', 'MCX', 'BFO'
    symbol_contains: substring match on the 'symbol' field, e.g. '24250CE', '04AUG26'

    Note: 'name' and 'symbol' are often different (e.g. name='ZENTEC',
    symbol='ZENTEC-EQ'), so callers unsure which the user gave should use
    find_token_by_lookup() instead, which tries both.
    """
    data = _load()
    results = []

    for d in data:
        if name and d.get("name") != name:
            continue
        if symbol and d.get("symbol") != symbol:
            continue
        if exch_seg and d.get("exch_seg") != exch_seg:
            continue
        if symbol_contains and symbol_contains.upper() not in d.get("symbol", "").upper():
            continue
        results.append(d)
        if len(results) >= limit:
            break

    return results


def find_token_by_lookup(query, exch_seg=None, limit=20):
    """
    Resolve a user-supplied instrument string to scrip master entries,
    trying the most exact match first and falling back to looser matches:

      1. Exact 'symbol' match (e.g. 'ZENTEC-EQ', 'SBIN-EQ')
      2. Exact 'name' match (e.g. 'ZENTEC', 'SBIN')
      3. Substring match on 'symbol' (e.g. 'ZENTEC' -> 'ZENTEC-EQ')

    query: the instrument string as given by the user/CLI, e.g. 'ZENTEC-EQ' or 'ZENTEC'
    exch_seg: optional exchange filter, e.g. 'NSE', 'BSE', 'NFO', 'MCX', 'BFO'
    """
    if not query:
        return []

    results = find_token(symbol=query, exch_seg=exch_seg, limit=limit)
    if results:
        return results

    results = find_token(name=query, exch_seg=exch_seg, limit=limit)
    if results:
        return results

    return find_token(exch_seg=exch_seg, symbol_contains=query, limit=limit)
