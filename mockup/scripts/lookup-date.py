import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine.parcel_lookup import lookup

parser = argparse.ArgumentParser()
parser.add_argument('address_id')
parser.add_argument('as_of')
parser.add_argument('--year-built')
parser.add_argument('--units')
args = parser.parse_args()
print(json.dumps(lookup(args.address_id, args.as_of, args.year_built, args.units)))
