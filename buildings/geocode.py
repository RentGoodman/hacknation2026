import csv
import hashlib
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from .config import BASE, BENCHMARK, CACHE_DIR, VINTAGE

LAYERS = "Incorporated Places,Counties"


def _get(url, params, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** (i + 1))


def _h(text):
    return hashlib.sha1(text.encode()).hexdigest()[:10]


def batch_geographies(requests_rows, refresh=False):
    buf = io.StringIO()
    w = csv.writer(buf)
    for rec in requests_rows:
        w.writerow(rec)
    CACHE_DIR.mkdir(exist_ok=True)
    raw_path = CACHE_DIR / f"batch_geographies_{_h(buf.getvalue())}.csv"
    (CACHE_DIR / f"{raw_path.stem}_input.csv").write_text(buf.getvalue())
    if refresh or not raw_path.exists():
        for i in range(4):
            try:
                resp = requests.post(
                    f"{BASE}/geographies/addressbatch",
                    files={"addressFile": ("addresses.csv", buf.getvalue(), "text/csv")},
                    data={"benchmark": BENCHMARK, "vintage": VINTAGE},
                    timeout=600,
                )
                resp.raise_for_status()
                break
            except Exception:
                if i == 3:
                    raise
                time.sleep(2 ** (i + 1))
        raw_path.write_text(resp.text)
    out = {}
    for rec in csv.reader(io.StringIO(raw_path.read_text())):
        if not rec:
            continue
        rec += [""] * (12 - len(rec))
        aid, _inp, status, mtype, matched, coords, _tl, _side, st, cty = rec[:10]
        lon = lat = None
        if coords:
            lon, lat = (float(x) for x in coords.split(","))
        out[aid] = {
            "match_status": status, "match_type": mtype or None, "matched_address": matched or None,
            "lat": lat, "lon": lon, "state_fips": st or None,
            "county_fips": (st + cty) if st and cty else None,
        }
    return out


def _cached(name, fn):
    CACHE_DIR.mkdir(exist_ok=True)
    p = CACHE_DIR / name
    if p.exists():
        return json.loads(p.read_text())
    data = fn()
    p.write_text(json.dumps(data))
    return data


def oneline(aid, address):
    return _cached(f"oneline_{aid}_{_h(address)}.json", lambda: _get(
        f"{BASE}/geographies/onelineaddress",
        {"address": address, "benchmark": BENCHMARK, "vintage": VINTAGE, "format": "json", "layers": LAYERS},
    ))


def coordinates(aid, lat, lon):
    return _cached(f"coords_{aid}_{lat:.6f}_{lon:.6f}.json", lambda: _get(
        f"{BASE}/geographies/coordinates",
        {"x": lon, "y": lat, "benchmark": BENCHMARK, "vintage": VINTAGE, "format": "json", "layers": LAYERS},
    ))


def parallel(fn, jobs, workers=12):
    with ThreadPoolExecutor(workers) as ex:
        results = list(ex.map(lambda a: (a[0], _safe(fn, *a)), jobs))
    return dict(results)


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception as e:
        return {"error": str(e)}


def parse_geographies(geos):
    places = geos.get("Incorporated Places") or []
    counties = geos.get("Counties") or []
    p = places[0] if places else None
    c = counties[0] if counties else None
    return {
        "place_name": p["NAME"] if p else None,
        "place_fips": p["GEOID"] if p else None,
        "county": c["NAME"] if c else None,
        "county_fips": c["GEOID"] if c else None,
    }
