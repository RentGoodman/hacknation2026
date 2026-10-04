from __future__ import annotations

import os
import urllib.request

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

TIGER_YEAR = 2025
STATES = ("06", "34", "25")
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "tiger")
COLUMNS = ["GEOID", "NAME", "NAMELSAD", "STATEFP", "LSAD", "CLASSFP", "geometry"]

_places = None


def _zip_path(state: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    name = f"tl_{TIGER_YEAR}_{state}_place.zip"
    path = os.path.join(CACHE_DIR, name)
    if not os.path.exists(path):
        url = f"https://www2.census.gov/geo/tiger/TIGER{TIGER_YEAR}/PLACE/{name}"
        tmp = path + ".part"
        urllib.request.urlretrieve(url, tmp)
        os.replace(tmp, path)
    return path


def load_places() -> gpd.GeoDataFrame:
    global _places
    if _places is None:
        frames = [gpd.read_file(_zip_path(s))[COLUMNS] for s in STATES]
        gdf = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
        _places = gdf.to_crs(4326)
    return _places


def lookup(points: dict) -> dict:
    empty = {"place_geoid": None, "place_name": None, "place_class": None}
    out = {k: dict(empty) for k in points}
    if not points:
        return out
    places = load_places()
    places = places[~places["CLASSFP"].str.startswith("U")]
    ids = list(points)
    pts = gpd.GeoDataFrame(
        {"address_id": ids},
        geometry=[Point(points[k][1], points[k][0]) for k in ids],
        crs=4326,
    )
    joined = gpd.sjoin(pts, places, how="inner", predicate="within")
    for _, r in joined.drop_duplicates("address_id").iterrows():
        out[r["address_id"]] = {
            "place_geoid": r["GEOID"],
            "place_name": r["NAMELSAD"],
            "place_class": r["CLASSFP"],
        }
    return out


if __name__ == "__main__":
    print(lookup({"t1": (34.096133, -118.324865), "t2": (42.30, -71.06)}))
