import hashlib
import json
import re
from datetime import date
from functools import lru_cache

from .rules import ROOT
from .run import evaluation_rules
from .verdict import verdicts_for_building


@lru_cache(maxsize=1)
def _inputs():
    raw = (ROOT / 'out/rules.json').read_bytes()
    buildings = json.loads((ROOT / 'out/buildings.json').read_text())
    return buildings, evaluation_rules(fetch=False), hashlib.sha256(raw).hexdigest()


def lookup(address_id, as_of, year_built=None, units=None):
    if not isinstance(address_id, str) or not re.fullmatch(r'A[0-9]{4}', address_id):
        raise ValueError('Invalid address')
    if not isinstance(as_of, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', as_of):
        raise ValueError('Invalid date')
    if date.fromisoformat(as_of).isoformat() != as_of:
        raise ValueError('Invalid date')
    overrides = {}
    if year_built is not None:
        if not re.fullmatch(r'\d{4}', str(year_built)) or not 1600 <= int(year_built) <= date.today().year:
            raise ValueError('Invalid year built')
        overrides['year_built'] = int(year_built)
    if units is not None:
        if not re.fullmatch(r'[1-9]\d{0,5}', str(units)) or not 1 <= int(units) <= 100000:
            raise ValueError('Invalid unit count')
        overrides['units'] = int(units)
    buildings, rules, rules_hash = _inputs()
    if address_id not in buildings:
        raise ValueError('Unknown address')
    building = dict(buildings[address_id])
    if 'year_built' in overrides:
        year = overrides['year_built']
        building.update(year_built=year, year_built_max=year,
                        year_built_max_method='user-supplied hypothetical',
                        co_date_min=f'{year}-01-01', co_date_max=f'{year}-12-31',
                        co_date_method='user-supplied year proxy; exact certificate date unknown')
    if 'units' in overrides:
        count = overrides['units']
        building.update(units=count, units_min=count, units_max=count,
                        units_method='user-supplied hypothetical')
    return {'address_id': address_id, 'as_of': as_of, 'fact_overrides': overrides,
            'rules_sha256': rules_hash,
            'lookups': verdicts_for_building(building, rules, as_of)}
