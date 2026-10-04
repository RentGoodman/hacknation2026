# Buildings report (Part 2)

Rows: 500 in, 500 out (all CSV ids present once).


## Counts per legal city

| legal city | count |
|---|---|
| Berkeley, CA | 40 |
| Boston, MA | 60 |
| Cambridge, MA | 50 |
| Hoboken, NJ | 40 |
| Jersey City, NJ | 50 |
| Los Angeles, CA | 80 |
| Newark, NJ | 50 |
| San Diego, CA | 50 |
| San Francisco, CA | 80 |

## Counts per legal city and county

| legal city / county | count |
|---|---|
| Berkeley, CA / Alameda County | 40 |
| Boston, MA / Suffolk County | 60 |
| Cambridge, MA / Middlesex County | 50 |
| Hoboken, NJ / Hudson County | 40 |
| Jersey City, NJ / Hudson County | 50 |
| Los Angeles, CA / Los Angeles County | 80 |
| Newark, NJ / Essex County | 50 |
| San Diego, CA / San Diego County | 50 |
| San Francisco, CA / San Francisco County | 80 |

## City status

| city_status | count |
|---|---|
| postal_fallback | 1 |
| resolved | 487 |
| resolved_by_mod_iv_municipality | 4 |
| resolved_by_source_dataset | 8 |

## Geocode status

| status | count |
|---|---|
| approximate | 45 |
| exact | 426 |
| failed | 7 |
| manual_review | 22 |

## Flags

| flag | count |
|---|---|
| ambiguous_match | 6 |
| approximate_match | 45 |
| city_from_mod_iv_municipality | 4 |
| city_from_source_dataset | 8 |
| geocode_failed | 7 |
| jurisdiction_mismatch | 38 |
| manual_review | 22 |
| postal_fallback | 1 |
| threshold_year_case | 2 |
| units_conflict | 3 |
| zip_suspect | 140 |

## Jurisdiction mismatches (postal city differs from legal city) (38)

| id | input address | postal city | legal city | county | status | normalized address |
|---|---|---|---|---|---|---|
| A0036 | 33 WARD ST, South Boston, MA 02127 | South Boston | Boston, MA | Suffolk County | exact | 33 WARD ST, SOUTH BOSTON, MA, 02127 |
| A0048 | 1619 COMMONWEALTH AV, Brighton, MA 02135 | Brighton | Boston, MA | Suffolk County | exact | 1619 COMMONWEALTH AVE, BRIGHTON, MA, 02135 |
| A0052 | 88 Gardner ST, Allston, MA 02134 | Allston | Boston, MA | Suffolk County | exact | 88 GARDNER ST, ALLSTON, MA, 02134 |
| A0054 | 13 Shetland ST, Roxbury, MA 02119 | Roxbury | Boston, MA | Suffolk County | exact | 13 SHETLAND ST, ROXBURY, MA, 02119 |
| A0065 | 63 Bailey ST, Dorchester, MA 02124 | Dorchester | Boston, MA | Suffolk County | exact | 63 BAILEY ST, DORCHESTER, MA, 02124 |
| A0083 | 38 KENILWORTH ST, Roxbury, MA 02119 | Roxbury | Boston, MA | Suffolk County | exact | 38 KENILWORTH ST, ROXBURY, MA, 02119 |
| A0093 | 90 BICKFORD ST, Jamaica Plain, MA 02130 | Jamaica Plain | Boston, MA | Suffolk County | exact | 90 BICKFORD ST, JAMAICA PLAIN, MA, 02130 |
| A0098 | WILLOWWOOD ST, Dorchester, MA 02124 | Dorchester | Boston, MA | Suffolk County | failed | - |
| A0118 | 18-34 KINGBIRD RD, Dorchester, MA 02124 | Dorchester | Boston, MA | Suffolk County | exact | 18 KINGBIRD RD, DORCHESTER, MA, 02124 |
| A0123 | 123 Condor ST, East Boston, MA 02128 | East Boston | Boston, MA | Suffolk County | exact | 123 CONDOR ST, EAST BOSTON, MA, 02128 |
| A0128 | Harvard ST, Dorchester, MA 02124 | Dorchester | Boston, MA | Suffolk County | failed | - |
| A0134 | 101 Norfolk ST, Dorchester, MA 02124 | Dorchester | Boston, MA | Suffolk County | exact | 101 NORFOLK ST, DORCHESTER, MA, 02124 |
| A0143 | 75 ELM HILL AV, Dorchester, MA 02121 | Dorchester | Boston, MA | Suffolk County | exact | 75 ELM HILL AVE, DORCHESTER, MA, 02121 |
| A0144 | 112-114 Amory ST, Roxbury, MA 02119 | Roxbury | Boston, MA | Suffolk County | exact | 112 AMORY ST, ROXBURY, MA, 02119 |
| A0149 | 25 Everett ST, East Boston, MA 02128 | East Boston | Boston, MA | Suffolk County | exact | 25 EVERETT ST, EAST BOSTON, MA, 02128 |
| A0155 | 473 Harvard ST, Dorchester, MA 02124 | Dorchester | Boston, MA | Suffolk County | exact | 473 HARVARD ST, DORCHESTER, MA, 02124 |
| A0169 | 115 KILSYTH RD, Brighton, MA 02135 | Brighton | Boston, MA | Suffolk County | exact | 115 KILSYTH RD, BRIGHTON, MA, 02135 |
| A0195 | 1850-1848 COMMONWEALTH AV, Brighton, MA 02135 | Brighton | Boston, MA | Suffolk County | exact | 1850 COMMONWEALTH AVE, BRIGHTON, MA, 02135 |
| A0198 | 194 Havre ST, East Boston, MA 02128 | East Boston | Boston, MA | Suffolk County | exact | 194 HAVRE ST, EAST BOSTON, MA, 02128 |
| A0203 | 2986-2930 Washington ST, Roxbury, MA 02119 | Roxbury | Boston, MA | Suffolk County | exact | 2986 WASHINGTON ST, ROXBURY, MA, 02119 |
| A0217 | 170-172 Maverick ST, East Boston, MA 02128 | East Boston | Boston, MA | Suffolk County | exact | 170 MAVERICK ST, EAST BOSTON, MA, 02128 |
| A0220 | 21-23 Faulkner ST, Dorchester, MA 02122 | Dorchester | Boston, MA | Suffolk County | exact | 21 FAULKNER ST, DORCHESTER, MA, 02122 |
| A0242 | 85-87 SIERRA RD, Hyde Park, MA 02136 | Hyde Park | Boston, MA | Suffolk County | manual_review | 87 SIERRA RD, HYDE PARK, MA, 02136 |
| A0245 | 30 WEST HOWELL ST M-D, Dorchester, MA 02125 | Dorchester | Boston, MA | Suffolk County | manual_review | 30 W HOWELL ST, DORCHESTER, MA, 02125 |
| A0258 | 471 COLUMBIA RD, Dorchester, MA 02125 | Dorchester | Boston, MA | Suffolk County | exact | 471 COLUMBIA RD, DORCHESTER, MA, 02125 |
| A0295 | Harvard ST LOT 2A-13, Dorchester, MA 02124 | Dorchester | Boston, MA | Suffolk County | failed | - |
| A0310 | 53-55 Ashford ST, Allston, MA 02134 | Allston | Boston, MA | Suffolk County | exact | 53 ASHFORD ST, ALLSTON, MA, 02134 |
| A0312 | 25 ORLANDO ST, Mattapan, MA 02126 | Mattapan | Boston, MA | Suffolk County | exact | 25 ORLANDO ST, MATTAPAN, MA, 02126 |
| A0322 | 227 CYPRESS DR, San Ysidro, CA 92173 | San Ysidro | San Diego, CA | San Diego County | exact | 227 CYPRESS DR, SAN YSIDRO, CA, 92173 |
| A0332 | 26 SONOMA ST, Dorchester, MA 02121 | Dorchester | Boston, MA | Suffolk County | exact | 26 SONOMA ST, DORCHESTER, MA, 02121 |
| A0354 | 73 LUBEC ST, East Boston, MA 02128 | East Boston | Boston, MA | Suffolk County | exact | 73 LUBEC ST, EAST BOSTON, MA, 02128 |
| A0356 | 16 Brainerd RD, Allston, MA 02134 | Allston | Boston, MA | Suffolk County | exact | 16 BRAINERD RD, ALLSTON, MA, 02134 |
| A0366 | 230 Everett ST, East Boston, MA 02128 | East Boston | Boston, MA | Suffolk County | exact | 230 EVERETT ST, EAST BOSTON, MA, 02128 |
| A0376 | ST JAMES ST, Roxbury, MA 02119 | Roxbury | Boston, MA | Suffolk County | failed | - |
| A0380 | GREENVILLE ST, Roxbury, MA 02119 | Roxbury | Boston, MA | Suffolk County | failed | - |
| A0423 | 10 CAMELOT CT, Brighton, MA 02135 | Brighton | Boston, MA | Suffolk County | exact | 10 CAMELOT CT, BRIGHTON, MA, 02135 |
| A0463 | 4 BEECHWOOD ST, Dorchester, MA 02121 | Dorchester | Boston, MA | Suffolk County | exact | 4 BEECHWOOD ST, DORCHESTER, MA, 02121 |
| A0464 | 2-98 DABNEY ST, Roxbury, MA 02119 | Roxbury | Boston, MA | Suffolk County | exact | 2 DABNEY ST, ROXBURY, MA, 02119 |

## Failed (7)

| id | input address | postal city | legal city | county | status | normalized address |
|---|---|---|---|---|---|---|
| A0098 | WILLOWWOOD ST, Dorchester, MA 02124 | Dorchester | Boston, MA | Suffolk County | failed | - |
| A0128 | Harvard ST, Dorchester, MA 02124 | Dorchester | Boston, MA | Suffolk County | failed | - |
| A0295 | Harvard ST LOT 2A-13, Dorchester, MA 02124 | Dorchester | Boston, MA | Suffolk County | failed | - |
| A0346 | AUBURN DR, San Diego, CA 92105 | San Diego | San Diego, CA | San Diego County | failed | - |
| A0376 | ST JAMES ST, Roxbury, MA 02119 | Roxbury | Boston, MA | Suffolk County | failed | - |
| A0380 | GREENVILLE ST, Roxbury, MA 02119 | Roxbury | Boston, MA | Suffolk County | failed | - |
| A0384 | 21 GUERRERO ST, San Francisco, CA | San Francisco | San Francisco, CA | San Francisco County | failed | - |

## Manual review (22)

Approximate match whose matched city or state disagrees with the input, or several candidates (ambiguous_match).

| id | input address | postal city | legal city | county | status | normalized address |
|---|---|---|---|---|---|---|
| A0028 | 585 5TH ST, Newark, NJ 07107 | Newark | Newark, NJ | Essex County | manual_review | 585 N 5TH ST, NEWARK, NJ, 07107 |
| A0071 | 14.5-16 Vandine St, Cambridge, MA | Cambridge | Cambridge, MA | Middlesex County | manual_review | 16 VANDINE ST, CAMBRIDGE, MA, 02141 |
| A0104 | 409 5TH ST, Newark, NJ 07012 | Newark | Newark, NJ | Essex County | manual_review | 409 N 5TH ST, NEWARK, NJ, 07107 |
| A0127 | 10029 SEPULVEDA BLVD, Los Angeles, CA 91345 | Los Angeles | Los Angeles, CA | Los Angeles County | manual_review | 10029 N SEPULVEDA BLVD, MISSION HILLS, CA, 91345 |
| A0137 | 65-71 NORFLOK ST, Newark, NJ 07003 | Newark | Newark, NJ | Essex County | manual_review | 65 NORFOLK ST, NEWARK, NJ, 07103 |
| A0150 | 3784 E BROADWAY, San Diego, CA 92102 | San Diego | San Diego, CA | San Diego County | manual_review | 3784 BROADWAY, SAN DIEGO, CA, 92102 |
| A0156 | 290 GREEN ST, San Francisco, CA | San Francisco | San Francisco, CA | San Francisco County | manual_review | - |
| A0168 | 600 JACKSON/601 HARRISON, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | manual_review | 600 JACKSON ST, HOBOKEN, NJ, 07030 |
| A0242 | 85-87 SIERRA RD, Hyde Park, MA 02136 | Hyde Park | Boston, MA | Suffolk County | manual_review | 87 SIERRA RD, HYDE PARK, MA, 02136 |
| A0245 | 30 WEST HOWELL ST M-D, Dorchester, MA 02125 | Dorchester | Boston, MA | Suffolk County | manual_review | 30 W HOWELL ST, DORCHESTER, MA, 02125 |
| A0262 | 2924 E JUNIPER ST, San Diego, CA 92104 | San Diego | San Diego, CA | San Diego County | manual_review | 2924 JUNIPER ST, SAN DIEGO, CA, 92104 |
| A0279 | 90 KENSINGTON AVE., Jersey City, NJ 07302 | Jersey City | Jersey City, NJ | Hudson County | manual_review | - |
| A0291 | 165 Cambridgepark Dr, Cambridge, MA | Cambridge | Cambridge, MA | Middlesex County | manual_review | - |
| A0343 | 408-410 5TH ST, Newark, NJ 10997 | Newark | Newark, NJ | Essex County | manual_review | 408 N 5TH ST, NEWARK, NJ, 07107 |
| A0344 | 238 & 242 GARFIELD AVE., Jersey City, NJ 07304 | Jersey City | Jersey City, NJ | Hudson County | manual_review | 242 GARFIELD AVE, JERSEY CITY, NJ, 07305 |
| A0352 | 40-42 MT PROSPECT AVE, Newark, NJ 07083 | Newark | Newark, NJ | Essex County | manual_review | - |
| A0392 | 4545 N 39TH ST, San Diego, CA 92116 | San Diego | San Diego, CA | San Diego County | manual_review | 4545 39TH ST, SAN DIEGO, CA, 92116 |
| A0400 | 174 MT PROSPECT AVE, Newark, NJ 07107 | Newark | Newark, NJ | Essex County | manual_review | - |
| A0421 | 17106 CHATSWORTH ST   APT 0001, Los Angeles, CA 91344 | Los Angeles | Los Angeles, CA | Los Angeles County | manual_review | 17106 CHATSWORTH ST, GRANADA HILLS, CA, 91344 |
| A0427 | 7665 FOUNTAIN AVE, Los Angeles, CA 90046 | Los Angeles | Los Angeles, CA | Los Angeles County | manual_review | 7665 W FOUNTAIN AVE, LOS ANGELES, CA, 90046 |
| A0428 | 312-314 MT PROSPECT AVE, Newark, NJ 07109 | Newark | Newark, NJ | Essex County | manual_review | - |
| A0480 | 4046 N 43RD ST, San Diego, CA 92105 | San Diego | San Diego, CA | San Diego County | manual_review | 4046 43RD ST, SAN DIEGO, CA, 92105 |

## Legal city unresolved (0)

city_status postal_only, no_place or not_geocoded.

None.

## City resolved by source dataset scope (8)

Point lookup failed; single-city source dataset (Boston, DataSF, Cambridge) gives the city.

| id | input address | postal city | legal city | county | status | normalized address |
|---|---|---|---|---|---|---|
| A0098 | WILLOWWOOD ST, Dorchester, MA 02124 | Dorchester | Boston, MA | Suffolk County | failed | - |
| A0128 | Harvard ST, Dorchester, MA 02124 | Dorchester | Boston, MA | Suffolk County | failed | - |
| A0156 | 290 GREEN ST, San Francisco, CA | San Francisco | San Francisco, CA | San Francisco County | manual_review | - |
| A0291 | 165 Cambridgepark Dr, Cambridge, MA | Cambridge | Cambridge, MA | Middlesex County | manual_review | - |
| A0295 | Harvard ST LOT 2A-13, Dorchester, MA 02124 | Dorchester | Boston, MA | Suffolk County | failed | - |
| A0376 | ST JAMES ST, Roxbury, MA 02119 | Roxbury | Boston, MA | Suffolk County | failed | - |
| A0380 | GREENVILLE ST, Roxbury, MA 02119 | Roxbury | Boston, MA | Suffolk County | failed | - |
| A0384 | 21 GUERRERO ST, San Francisco, CA | San Francisco | San Francisco, CA | San Francisco County | failed | - |

## Postal city only (legal city unknown) (0)

Multi-city source dataset; legal_city stays null, legal_city_candidate holds the postal city. Part 3 must answer unknown for city-level rules.

None.

## Suspect ZIP (not sent to the Census) (140)

| id | input address | postal city | legal city | county | status | normalized address |
|---|---|---|---|---|---|---|
| A0002 | 1031-1035 CLINTON ST, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 1031 CLINTON ST, HOBOKEN, NJ, 07030 |
| A0003 | 876-878 S 14TH ST, Newark, NJ 11219 | Newark | Newark, NJ | Essex County | exact | 876 S 14TH ST, NEWARK, NJ, 07108 |
| A0008 | 1065 SUMMIT AVENUE, Jersey City, NJ 78746 | Jersey City | Jersey City, NJ | Hudson County | exact | 1065 SUMMIT AVE, JERSEY CITY, NJ, 07307 |
| A0011 | 834-836 RAYMOND BLVD, Newark, NJ 08805 | Newark | Newark, NJ | Essex County | exact | 834 RAYMOND BLVD, NEWARK, NJ, 07105 |
| A0012 | 1064 SUMMIT AVE., Jersey City, NJ 07728 | Jersey City | Jersey City, NJ | Hudson County | exact | 1064 SUMMIT AVE, JERSEY CITY, NJ, 07307 |
| A0013 | 137 N 11TH ST, Newark, NJ 07107 | Newark | Newark, NJ | Essex County | exact | 137 N 11TH ST, NEWARK, NJ, 07107 |
| A0017 | 225 DUNCAN AVE., Jersey City, NJ 10949 | Jersey City | Jersey City, NJ | Hudson County | exact | 225 DUNCAN AVE, JERSEY CITY, NJ, 07306 |
| A0020 | 646-648 N 6TH ST, Newark, NJ 07083 | Newark | Newark, NJ | Essex County | exact | 646 N 6TH ST, NEWARK, NJ, 07107 |
| A0026 | 59 OAK ST., Jersey City, NJ 07306 | Jersey City | Jersey City, NJ | Hudson County | exact | 59 OAK ST, JERSEY CITY, NJ, 07304 |
| A0028 | 585 5TH ST, Newark, NJ 07107 | Newark | Newark, NJ | Essex County | manual_review | 585 N 5TH ST, NEWARK, NJ, 07107 |
| A0029 | 280-284 VERONA AVE, Newark, NJ 07653 | Newark | Newark, NJ | Essex County | exact | 280 VERONA AVE, NEWARK, NJ, 07104 |
| A0032 | 63 OAK ST., Jersey City, NJ 08820 | Jersey City | Jersey City, NJ | Hudson County | exact | 63 OAK ST, JERSEY CITY, NJ, 07304 |
| A0040 | 69-75 JACKSON ST, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 69 JACKSON ST, HOBOKEN, NJ, 07030 |
| A0042 | 320 FORREST ST., Jersey City, NJ 07304 | Jersey City | Jersey City, NJ | Hudson County | exact | 320 FORREST ST, JERSEY CITY, NJ, 07304 |
| A0044 | 773-775 SANDFORD AVE, Newark, NJ 11211 | Newark | Newark, NJ | Essex County | exact | 773 SANDFORD AVE, NEWARK, NJ, 07106 |
| A0047 | 14 RUTGERS AVE., Jersey City, NJ 07304 | Jersey City | Jersey City, NJ | Hudson County | exact | 14 RUTGERS AVE, JERSEY CITY, NJ, 07305 |
| A0049 | 721 CLINTON ST, Hoboken, NJ 07856 | Hoboken | Hoboken, NJ | Hudson County | exact | 721 CLINTON ST, HOBOKEN, NJ, 07030 |
| A0051 | 65 OAKLAND AVE., Jersey City, NJ 07423 | Jersey City | Jersey City, NJ | Hudson County | exact | 65 OAKLAND AVE, JERSEY CITY, NJ, 07306 |
| A0057 | 57 STONE ST, Newark, NJ 07012 | Newark | Newark, NJ | Essex County | exact | 57 STONE ST, NEWARK, NJ, 07104 |
| A0059 | 84-86 WALNUT ST, Newark, NJ 07078 | Newark | Newark, NJ | Essex County | exact | 84 WALNUT ST, NEWARK, NJ, 07102 |
| A0076 | 304 E KINNEY ST, Newark, NJ 07033 | Newark | Newark, NJ | Essex County | exact | 304 E KINNEY ST, NEWARK, NJ, 07105 |
| A0078 | 115 BAYVIEW AVE., Jersey City, NJ 07304 | Jersey City | Jersey City, NJ | Hudson County | exact | 115 BAYVIEW AVE, JERSEY CITY, NJ, 07305 |
| A0087 | 323 BLOOMFIELD ST, Hoboken, NJ 07504 | Hoboken | Hoboken, NJ | Hudson County | exact | 323 BLOOMFIELD ST, HOBOKEN, NJ, 07030 |
| A0089 | 935 PARK AVE, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 935 PARK AVE, HOBOKEN, NJ, 07030 |
| A0090 | 30 JACKSON ST, Newark, NJ 07105 | Newark | Newark, NJ | Essex County | exact | 30 JACKSON ST, NEWARK, NJ, 07105 |
| A0099 | 822 WASHINGTON ST, Hoboken, NJ 07458 | Hoboken | Hoboken, NJ | Hudson County | exact | 822 WASHINGTON ST, HOBOKEN, NJ, 07030 |
| A0101 | 315-319 FAIRMOUNT AVENUE, Jersey City, NJ 07039 | Jersey City | Jersey City, NJ | Hudson County | exact | 315 FAIRMOUNT AVE, JERSEY CITY, NJ, 07306 |
| A0102 | 124 BLOOMFIELD ST, Hoboken, NJ 10003 | Hoboken | Hoboken, NJ | Hudson County | exact | 124 BLOOMFIELD ST, HOBOKEN, NJ, 07030 |
| A0104 | 409 5TH ST, Newark, NJ 07012 | Newark | Newark, NJ | Essex County | manual_review | 409 N 5TH ST, NEWARK, NJ, 07107 |
| A0108 | 13 JEFFERSON AVE., Jersey City, NJ 07030 | Jersey City | Jersey City, NJ | Hudson County | exact | 13 JEFFERSON AVE, JERSEY CITY, NJ, 07306 |
| A0110 | 130-132 2ND AVE, Newark, NJ 07055 | Newark | Newark, NJ | Essex County | exact | 130 2ND AVE, NEWARK, NJ, 07104 |
| A0116 | 36 PROSPECT ST., Jersey City, NJ 07111 | Jersey City | Jersey City, NJ | Hudson County | exact | 36 PROSPECT ST, JERSEY CITY, NJ, 07307 |
| A0119 | 607 ADAMS ST, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 607 ADAMS ST, HOBOKEN, NJ, 07030 |
| A0120 | 139 ELM ST, Newark, NJ 07105 | Newark | Newark, NJ | Essex County | exact | 139 ELM ST, NEWARK, NJ, 07105 |
| A0125 | 227 GRAND ST, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 227 GRAND ST, HOBOKEN, NJ, 07030 |
| A0129 | 526-532 MULBERRY ST, Newark, NJ 07039 | Newark | Newark, NJ | Essex County | exact | 526 MULBERRY ST, NEWARK, NJ, 07114 |
| A0130 | 554 MARKET ST, Newark, NJ 07205 | Newark | Newark, NJ | Essex County | exact | 554 MARKET ST, NEWARK, NJ, 07105 |
| A0131 | 43 POPLAR ST., Jersey City, NJ 07307 | Jersey City | Jersey City, NJ | Hudson County | exact | 43 POPLAR ST, JERSEY CITY, NJ, 07307 |
| A0132 | 587 N 6TH ST, Newark, NJ 11205 | Newark | Newark, NJ | Essex County | exact | 587 N 6TH ST, NEWARK, NJ, 07107 |
| A0136 | 920 HUDSON ST, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 920 HUDSON ST, HOBOKEN, NJ, 07030 |
| A0137 | 65-71 NORFLOK ST, Newark, NJ 07003 | Newark | Newark, NJ | Essex County | manual_review | 65 NORFOLK ST, NEWARK, NJ, 07103 |
| A0139 | 54 STUYVESANT AVE., Jersey City, NJ 07042 | Jersey City | Jersey City, NJ | Hudson County | exact | 54 STUYVESANT AVE, JERSEY CITY, NJ, 07306 |
| A0146 | 93-95 HAWKINS ST, Newark, NJ 07105 | Newark | Newark, NJ | Essex County | exact | 93 HAWKINS ST, NEWARK, NJ, 07105 |
| A0148 | 162-166 5TH ST, Newark, NJ 07105 | Newark | Newark, NJ | Essex County | exact | 162 5TH ST, NEWARK, NJ, 07107 |
| A0159 | 104 SUNSET AVE, Newark, NJ 11211 | Newark | Newark, NJ | Essex County | exact | 104 SUNSET AVE, NEWARK, NJ, 07106 |
| A0160 | 86 CHARLES ST., Jersey City, NJ 07642 | Jersey City | Jersey City, NJ | Hudson County | exact | 86 CHARLES ST, JERSEY CITY, NJ, 07307 |
| A0161 | 317 UNION ST., Jersey City, NJ 07013 | Jersey City | Jersey City, NJ | Hudson County | exact | 317 UNION ST, JERSEY CITY, NJ, 07304 |
| A0163 | 233-235 SECOND ST., Jersey City, NJ 07042 | Jersey City | Jersey City, NJ | Hudson County | exact | 233 2ND ST, JERSEY CITY, NJ, 07302 |
| A0168 | 600 JACKSON/601 HARRISON, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | manual_review | 600 JACKSON ST, HOBOKEN, NJ, 07030 |
| A0171 | 127 OGDEN AVE., Jersey City, NJ 07660 | Jersey City | Jersey City, NJ | Hudson County | exact | 127 OGDEN AVE, JERSEY CITY, NJ, 07307 |
| A0177 | 166 HIGHLAND AVE., Jersey City, NJ 11201 | Jersey City | Jersey City, NJ | Hudson County | exact | 166 HIGHLAND AVE, JERSEY CITY, NJ, 07306 |
| A0181 | 931 GARDEN ST, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 931 GARDEN ST, HOBOKEN, NJ, 07030 |
| A0182 | 911-923 CLINTON ST, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 911 CLINTON ST, HOBOKEN, NJ, 07030 |
| A0185 | 154 TERHUNE AVE., Jersey City, NJ 07103 | Jersey City | Jersey City, NJ | Hudson County | exact | 154 TERHUNE AVE, JERSEY CITY, NJ, 07305 |
| A0186 | 107 BEACON AVE., Jersey City, NJ 07306 | Jersey City | Jersey City, NJ | Hudson County | exact | 107 BEACON AVE, JERSEY CITY, NJ, 07306 |
| A0187 | 146 CARLTON AVE., Jersey City, NJ 07423 | Jersey City | Jersey City, NJ | Hudson County | exact | 146 CARLTON AVE, JERSEY CITY, NJ, 07306 |
| A0190 | 283 ADAMS ST, Newark, NJ 07105 | Newark | Newark, NJ | Essex County | exact | 283 ADAMS ST, NEWARK, NJ, 07105 |
| A0204 | 202-208 6TH AVE W, Newark, NJ 08736 | Newark | Newark, NJ | Essex County | exact | 202 6TH AVE W, NEWARK, NJ, 07107 |
| A0208 | 126 ADAMS ST, Hoboken, NJ 07604 | Hoboken | Hoboken, NJ | Hudson County | exact | 126 ADAMS ST, HOBOKEN, NJ, 07030 |
| A0223 | 504 COURT ST, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 504 COURT ST, HOBOKEN, NJ, 07030 |
| A0227 | 1401 HUDSON ST, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 1401 HUDSON ST, HOBOKEN, NJ, 07030 |
| A0241 | 913 GARDEN ST, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 913 GARDEN ST, HOBOKEN, NJ, 07030 |
| A0243 | 664 OCEAN AVE., Jersey City, NJ 07305 | Jersey City | Jersey City, NJ | Hudson County | exact | 664 OCEAN AVE, JERSEY CITY, NJ, 07305 |
| A0244 | 1126 HUDSON ST, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 1126 HUDSON ST, HOBOKEN, NJ, 07030 |
| A0249 | 498-500 HAWTHORNE AVE, Newark, NJ 10013 | Newark | Newark, NJ | Essex County | exact | 498 HAWTHORNE AVE, NEWARK, NJ, 07112 |
| A0250 | 211 BALDWIN AVE., Jersey City, NJ 07002 | Jersey City | Jersey City, NJ | Hudson County | exact | 211 BALDWIN AVE, JERSEY CITY, NJ, 07306 |
| A0254 | 805 WASHINGTON ST, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 805 WASHINGTON ST, HOBOKEN, NJ, 07030 |
| A0256 | 327 JACKSON ST, Hoboken, NJ 07017 | Hoboken | Hoboken, NJ | Hudson County | exact | 327 JACKSON ST, HOBOKEN, NJ, 07030 |
| A0261 | 525 ADAMS ST, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 525 ADAMS ST, HOBOKEN, NJ, 07030 |
| A0264 | 583-589 ELIZABETH AVE, Newark, NJ 11516 | Newark | Newark, NJ | Essex County | exact | 583 ELIZABETH AVE, NEWARK, NJ, 07112 |
| A0265 | 102 BALDWIN AVE., Jersey City, NJ 07306 | Jersey City | Jersey City, NJ | Hudson County | exact | 102 BALDWIN AVE, JERSEY CITY, NJ, 07306 |
| A0266 | 52 BRIGHT ST., Jersey City, NJ 10016 | Jersey City | Jersey City, NJ | Hudson County | exact | 52 BRIGHT ST, JERSEY CITY, NJ, 07302 |
| A0269 | 1015 CLINTON ST, Hoboken, NJ 10003 | Hoboken | Hoboken, NJ | Hudson County | exact | 1015 CLINTON ST, HOBOKEN, NJ, 07030 |
| A0270 | 29 CONCORD ST, Jersey City, NJ 07306 | Jersey City | Jersey City, NJ | Hudson County | exact | 29 CONCORD ST, JERSEY CITY, NJ, 07306 |
| A0279 | 90 KENSINGTON AVE., Jersey City, NJ 07302 | Jersey City | Jersey City, NJ | Hudson County | manual_review | - |
| A0287 | 404 GRAND ST, Hoboken, NJ 07075 | Hoboken | Hoboken, NJ | Hudson County | exact | 404 GRAND ST, HOBOKEN, NJ, 07030 |
| A0288 | 75 CLENDENNY AVE., Jersey City, NJ 11211 | Jersey City | Jersey City, NJ | Hudson County | exact | 75 CLENDENNY AVE, JERSEY CITY, NJ, 07304 |
| A0296 | 83-85 MCWHORTER ST, Newark, NJ 07105 | Newark | Newark, NJ | Essex County | exact | 83 MCWHORTER ST, NEWARK, NJ, 07105 |
| A0297 | 211-213 SUMMER AVE, Newark, NJ 11205 | Newark | Newark, NJ | Essex County | exact | 211 SUMMER AVE, NEWARK, NJ, 07104 |
| A0299 | 1037 WASHINGTON ST, Hoboken, NJ 10994 | Hoboken | Hoboken, NJ | Hudson County | exact | 1037 WASHINGTON ST, HOBOKEN, NJ, 07030 |
| A0307 | 294-296 VAN BUREN ST, Newark, NJ 07512 | Newark | Newark, NJ | Essex County | exact | 294 VAN BUREN ST, NEWARK, NJ, 07105 |
| A0308 | 1032 HUDSON ST, Hoboken, NJ 07024 | Hoboken | Hoboken, NJ | Hudson County | exact | 1032 HUDSON ST, HOBOKEN, NJ, 07030 |
| A0311 | 38-38- SOMME ST, Newark, NJ 07032 | Newark | Newark, NJ | Essex County | exact | 38 SOMME ST, NEWARK, NJ, 07105 |
| A0313 | 317-319 W RUNYON ST, Newark, NJ 11205 | Newark | Newark, NJ | Essex County | exact | 317 W RUNYON ST, NEWARK, NJ, 07108 |
| A0320 | 408 MADISON ST, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 408 MADISON ST, HOBOKEN, NJ, 07030 |
| A0321 | 200 NUNDA AVE., Jersey City, NJ 07306 | Jersey City | Jersey City, NJ | Hudson County | exact | 200 NUNDA AVE, JERSEY CITY, NJ, 07306 |
| A0325 | 38A GAUTIER AVE., Jersey City, NJ 07302 | Jersey City | Jersey City, NJ | Hudson County | approximate | 38A GAUTIER AVE, JERSEY CITY, NJ, 07306 |
| A0326 | 46 JEFFERSON ST, Newark, NJ 07105 | Newark | Newark, NJ | Essex County | exact | 46 JEFFERSON ST, NEWARK, NJ, 07105 |
| A0329 | 51 MADISON ST, Newark, NJ 07105 | Newark | Newark, NJ | Essex County | exact | 51 MADISON ST, NEWARK, NJ, 07105 |
| A0331 | 342-344 IRVINE TURNER BLV, Newark, NJ 11219 | Newark | Newark, NJ | Essex County | exact | 342 IRVINE TURNER BLVD, NEWARK, NJ, 07108 |
| A0337 | 66 MONROE ST, Newark, NJ 07032 | Newark | Newark, NJ | Essex County | exact | 66 MONROE ST, NEWARK, NJ, 07105 |
| A0338 | 521-523 S 17TH, Newark, NJ 07417 | Newark | Newark, NJ | Essex County | approximate | 521 S 17TH ST, NEWARK, NJ, 07103 |
| A0343 | 408-410 5TH ST, Newark, NJ 10997 | Newark | Newark, NJ | Essex County | manual_review | 408 N 5TH ST, NEWARK, NJ, 07107 |
| A0344 | 238 & 242 GARFIELD AVE., Jersey City, NJ 07304 | Jersey City | Jersey City, NJ | Hudson County | manual_review | 242 GARFIELD AVE, JERSEY CITY, NJ, 07305 |
| A0348 | 229 CLINTON ST, Hoboken, NJ 08755 | Hoboken | Hoboken, NJ | Hudson County | exact | 229 CLINTON ST, HOBOKEN, NJ, 07030 |
| A0350 | 1051 WEST SIDE AVE., Jersey City, NJ 07446 | Jersey City | Jersey City, NJ | Hudson County | exact | 1051 W SIDE AVE, JERSEY CITY, NJ, 07306 |
| A0352 | 40-42 MT PROSPECT AVE, Newark, NJ 07083 | Newark | Newark, NJ | Essex County | manual_review | - |
| A0358 | 717 N 6TH ST, Newark, NJ 07110 | Newark | Newark, NJ | Essex County | exact | 717 N 6TH ST, NEWARK, NJ, 07107 |
| A0359 | 925 PARK AVE, Hoboken, NJ 07306 | Hoboken | Hoboken, NJ | Hudson County | exact | 925 PARK AVE, HOBOKEN, NJ, 07030 |
| A0360 | 140 NEW YORK AVE., Jersey City, NJ 10977 | Jersey City | Jersey City, NJ | Hudson County | exact | 140 NEW YORK AVE, JERSEY CITY, NJ, 07307 |
| A0371 | 76-80 BRUEN ST, Newark, NJ 07105 | Newark | Newark, NJ | Essex County | exact | 76 BRUEN ST, NEWARK, NJ, 07105 |
| A0372 | 314 SEVENTH ST., Jersey City, NJ 07302 | Jersey City | Jersey City, NJ | Hudson County | exact | 314 7TH ST, JERSEY CITY, NJ, 07302 |
| A0377 | 206 BLOOMFIELD ST, Hoboken, NJ 10003 | Hoboken | Hoboken, NJ | Hudson County | exact | 206 BLOOMFIELD ST, HOBOKEN, NJ, 07030 |
| A0381 | 521-523 MARKET ST, Newark, NJ 07105 | Newark | Newark, NJ | Essex County | exact | 521 MARKET ST, NEWARK, NJ, 07105 |
| A0388 | 157-155 CLERK ST., Jersey City, NJ 07305 | Jersey City | Jersey City, NJ | Hudson County | exact | 157 CLERK ST, JERSEY CITY, NJ, 07305 |
| A0389 | 923 GARDEN ST, Hoboken, NJ 07068 | Hoboken | Hoboken, NJ | Hudson County | exact | 923 GARDEN ST, HOBOKEN, NJ, 07030 |
| A0390 | 70 DARCY ST, Newark, NJ 07202 | Newark | Newark, NJ | Essex County | exact | 70 DARCY ST, NEWARK, NJ, 07105 |
| A0393 | 91 JORDAN AVE., Jersey City, NJ 07081 | Jersey City | Jersey City, NJ | Hudson County | exact | 91 JORDAN AVE, JERSEY CITY, NJ, 07306 |
| A0394 | 45 RAVINE AVE., Jersey City, NJ 07302 | Jersey City | Jersey City, NJ | Hudson County | exact | 45 RAVINE AVE, JERSEY CITY, NJ, 07307 |
| A0399 | 227 WILLOW AVE, Hoboken, NJ 07643 | Hoboken | Hoboken, NJ | Hudson County | exact | 227 WILLOW AVE, HOBOKEN, NJ, 07030 |
| A0400 | 174 MT PROSPECT AVE, Newark, NJ 07107 | Newark | Newark, NJ | Essex County | manual_review | - |
| A0404 | 240 BOWERS ST., Jersey City, NJ 07603 | Jersey City | Jersey City, NJ | Hudson County | exact | 240 BOWERS ST, JERSEY CITY, NJ, 07307 |
| A0410 | 319 SUMMIT AVE., Jersey City, NJ 07306 | Jersey City | Jersey City, NJ | Hudson County | exact | 319 SUMMIT AVE, JERSEY CITY, NJ, 07306 |
| A0412 | 229-231 GRAFTON AVE, Newark, NJ 07003 | Newark | Newark, NJ | Essex County | exact | 229 GRAFTON AVE, NEWARK, NJ, 07104 |
| A0415 | 95 WAYNE ST., Jersey City, NJ 07302 | Jersey City | Jersey City, NJ | Hudson County | exact | 95 WAYNE ST, JERSEY CITY, NJ, 07302 |
| A0416 | 882 PAVONIA AVE., Jersey City, NJ 10281 | Jersey City | Jersey City, NJ | Hudson County | exact | 882 PAVONIA AVE, JERSEY CITY, NJ, 07306 |
| A0418 | 221 SIP AVE., Jersey City, NJ 07009 | Jersey City | Jersey City, NJ | Hudson County | exact | 221 SIP AVE, JERSEY CITY, NJ, 07306 |
| A0424 | 208 JEFFERSON ST, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 208 JEFFERSON ST, HOBOKEN, NJ, 07030 |
| A0428 | 312-314 MT PROSPECT AVE, Newark, NJ 07109 | Newark | Newark, NJ | Essex County | manual_review | - |
| A0435 | 310 MONROE ST, Hoboken, NJ 07632 | Hoboken | Hoboken, NJ | Hudson County | exact | 310 MONROE ST, HOBOKEN, NJ, 07030 |
| A0436 | 832 WILLOW AVE, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 832 WILLOW AVE, HOBOKEN, NJ, 07030 |
| A0438 | 60-62 CAMBRIDGE AVE, Jersey City, NJ 07430 | Jersey City | Jersey City, NJ | Hudson County | exact | 60 CAMBRIDGE AVE, JERSEY CITY, NJ, 07307 |
| A0447 | 208 CLINTON ST, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 208 CLINTON ST, HOBOKEN, NJ, 07030 |
| A0448 | 151-153 LAFAYETTE ST, Newark, NJ 07105 | Newark | Newark, NJ | Essex County | exact | 151 LAFAYETTE ST, NEWARK, NJ, 07105 |
| A0449 | 338 CLINTON PL, Newark, NJ 08701 | Newark | Newark, NJ | Essex County | exact | 338 CLINTON PL, NEWARK, NJ, 07112 |
| A0450 | 94 NEPTUNE AVE., Jersey City, NJ 11211 | Jersey City | Jersey City, NJ | Hudson County | exact | 94 NEPTUNE AVE, JERSEY CITY, NJ, 07305 |
| A0455 | 78 STEVENS AVE., Jersey City, NJ 07108 | Jersey City | Jersey City, NJ | Hudson County | exact | 78 STEVENS AVE, JERSEY CITY, NJ, 07305 |
| A0459 | 202 SOUTH ST., Jersey City, NJ 07423 | Jersey City | Jersey City, NJ | Hudson County | exact | 202 SOUTH ST, JERSEY CITY, NJ, 07307 |
| A0460 | 223-229 SHEPHARD AVE, Newark, NJ 11204 | Newark | Newark, NJ | Essex County | exact | 223 SHEPHARD AVE, NEWARK, NJ, 07112 |
| A0462 | 128 ST. PAULS AVE., Jersey City, NJ 11211 | Jersey City | Jersey City, NJ | Hudson County | exact | 128 ST PAULS AVE, JERSEY CITY, NJ, 07306 |
| A0471 | 332-334 GARDEN ST, Hoboken, NJ 07604 | Hoboken | Hoboken, NJ | Hudson County | exact | 332 GARDEN ST, HOBOKEN, NJ, 07030 |
| A0472 | 321 WILLOW AVE, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 321 WILLOW AVE, HOBOKEN, NJ, 07030 |
| A0475 | 361 FIRST ST, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 361 1ST ST, HOBOKEN, NJ, 07030 |
| A0476 | 26-28 COTTAGE ST, Newark, NJ 07840 | Newark | Newark, NJ | Essex County | exact | 26 COTTAGE ST, NEWARK, NJ, 07102 |
| A0482 | 101 CLIFTON PL., Jersey City, NJ 10982 | Jersey City | Jersey City, NJ | Hudson County | exact | 101 CLIFTON PL, JERSEY CITY, NJ, 07304 |
| A0489 | 204 GRAND ST, Hoboken, NJ 06901 | Hoboken | Hoboken, NJ | Hudson County | exact | 204 GRAND ST, HOBOKEN, NJ, 07030 |
| A0490 | 526 ADAMS ST, Hoboken, NJ 07030 | Hoboken | Hoboken, NJ | Hudson County | exact | 526 ADAMS ST, HOBOKEN, NJ, 07030 |
| A0491 | 37 IRVING ST, Newark, NJ 07104 | Newark | Newark, NJ | Essex County | exact | 37 IRVING ST, NEWARK, NJ, 07104 |
| A0495 | 230 VAN HORNE ST., Jersey City, NJ 11219 | Jersey City | Jersey City, NJ | Hudson County | exact | 230 VAN HORNE ST, JERSEY CITY, NJ, 07304 |
| A0498 | 684-686 SUMMER AVE, Newark, NJ 07644 | Newark | Newark, NJ | Essex County | exact | 684 SUMMER AVE, NEWARK, NJ, 07104 |

## Outside the 9 study cities (0)

None.

## Unincorporated (geocoded, no incorporated place) (0)

None.

## Public-source enrichment (buildings/enrich.py)

SANDAG parcels: 46 rows without year_built got year_built_max / co_date_max (44 with a year <= 2010). Berkeley: no public source with year built or unit count (see buildings/README.md).

## Missing facts per legal city

owner_type is missing on every row; certificate_of_occupancy_date is missing when year_built is unknown.

| legal city | rows | year_built | units | property_type |
|---|---|---|---|---|
| Berkeley, CA | 40 | 40 | 40 | 0 |
| Boston, MA | 60 | 8 | 60 | 0 |
| Cambridge, MA | 50 | 0 | 0 | 0 |
| Hoboken, NJ | 40 | 36 | 40 | 0 |
| Jersey City, NJ | 50 | 22 | 50 | 0 |
| Los Angeles, CA | 80 | 6 | 3 | 0 |
| Newark, NJ | 50 | 48 | 50 | 0 |
| San Diego, CA | 50 | 50 | 0 | 0 |
| San Francisco, CA | 80 | 2 | 2 | 0 |

## Unit counts: provenance

| units_method | buildings |
|---|---|
| class: Boston use_code A/118 | 1 |
| class: Boston use_code A/120 | 5 |
| class: Boston use_code A/125 | 26 |
| class: NJ MOD-IV use_code 4C | 50 |
| csv units field | 255 |
| explicit count in use_description | 90 |
| range in use_description | 73 |

Buildings without units and without a lower bound: 1: A0398 (TIC Bldg 4 units or less)

### Unit conflicts (3)

Contradicting number not used; interval or explicit count kept.

| id | use_description | units_raw | interval | method |
|---|---|---|---|---|
| A0041 | Apartment 5 to 14 Units | 15 | 5..15 | range in use_description (5 to 14 Units); interval widened to include conflicting CSV units 15 |
| A0227 | 13B-93U-2C-G | 2 | 2..93 | explicit count in use_description (13B-93U-2C-G); interval widened to include conflicting CSV units 2 |
| A0398 | TIC Bldg 4 units or less | 5 | None..5 | range in use_description (4 units or less); interval widened to include conflicting CSV units 5 |

## Census matches rejected for house number (0)

| id | source | sent | matched | reason |
|---|---|---|---|---|
None.

## Threshold year cases (2)

LA with year_built 1978 or SF with 1979: certificate of occupancy date unknown, Part 3 must answer unknown.

| id | input address | legal city | year_built |
|---|---|---|---|
| A0107 | 10635 SHERMAN GROVE AVE, Los Angeles, CA 91040 | Los Angeles, CA | 1978 |
| A0432 | 14605 RAYEN ST, Los Angeles, CA 91402 | Los Angeles, CA | 1978 |
