from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADDRESSES_CSV = ROOT / "starter pack" / "data" / "sample_addresses.csv"
PRIOR_CENSUS_CSV = ROOT / "mockup" / "inputs" / "data" / "census-results.csv"
CACHE_DIR = Path(__file__).resolve().parent / "cache"
OUT_DIR = ROOT / "out"
OUT_JSON = OUT_DIR / "buildings.json"
OUT_REPORT = OUT_DIR / "buildings_report.md"

BENCHMARK = "Public_AR_Current"
VINTAGE = "Current_Current"
BASE = "https://geocoding.geo.census.gov/geocoder"

EXPECTED_ROWS = 500

STUDY_CITIES = {
    "Los Angeles city": "Los Angeles",
    "San Francisco city": "San Francisco",
    "San Diego city": "San Diego",
    "Berkeley city": "Berkeley",
    "Jersey City city": "Jersey City",
    "Hoboken city": "Hoboken",
    "Newark city": "Newark",
    "Boston city": "Boston",
    "Cambridge city": "Cambridge",
}
EXPECTED_COUNTY = {
    "Los Angeles": ("CA", "06037", "Los Angeles County"),
    "San Francisco": ("CA", "06075", "San Francisco County"),
    "San Diego": ("CA", "06073", "San Diego County"),
    "Berkeley": ("CA", "06001", "Alameda County"),
    "Jersey City": ("NJ", "34017", "Hudson County"),
    "Hoboken": ("NJ", "34017", "Hudson County"),
    "Newark": ("NJ", "34013", "Essex County"),
    "Boston": ("MA", "25025", "Suffolk County"),
    "Cambridge": ("MA", "25017", "Middlesex County"),
}
EXPECTED_COUNTS = {
    "Los Angeles": 80, "San Francisco": 80, "San Diego": 50, "Berkeley": 40,
    "Jersey City": 50, "Hoboken": 40, "Newark": 50, "Boston": 60, "Cambridge": 50,
}
SOURCE_CITY = {
    "LA County eGIS parcels": "Los Angeles",
    "DataSF wv5m-vpq2 (2025 roll)": "San Francisco",
    "Alameda County parcels": "Berkeley",
    "Boston Property Assessment FY2026": "Boston",
    "Cambridge Property Database FY2026 (waa7-ibdu)": "Cambridge",
    "SANDAG/SanGIS parcels": "San Diego",
}
CUTOFF_AMBIGUOUS = {"San Francisco": 1979, "Los Angeles": 1978}
