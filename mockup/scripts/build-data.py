from pathlib import Path
import csv, json, os, re, hashlib, shutil
from source_bundle import load_sources, check_rule_sources, write_sources, write_starter
ROOT=Path(__file__).resolve().parents[1]
PACK=ROOT/'inputs'
OUT=ROOT/'dist/data'
OUT.mkdir(parents=True,exist_ok=True)
shutil.copyfile(PACK/'data/sample_addresses.csv',OUT/'sample_addresses.csv')
CITIES={
'sf':dict(name='San Francisco',state='CA',center=[-122.431,37.773],zoom=11.8),
'la':dict(name='Los Angeles',state='CA',center=[-118.34,34.10],zoom=10),
'sd':dict(name='San Diego',state='CA',center=[-117.13,32.75],zoom=10.5),
'berkeley':dict(name='Berkeley',state='CA',center=[-122.274,37.870],zoom=12),
'jc':dict(name='Jersey City',state='NJ',center=[-74.055,40.722],zoom=12),
'hoboken':dict(name='Hoboken',state='NJ',center=[-74.032,40.745],zoom=13),
'newark':dict(name='Newark',state='NJ',center=[-74.177,40.735],zoom=11.8),
'boston':dict(name='Boston',state='MA',center=[-71.08,42.32],zoom=11),
'cambridge':dict(name='Cambridge',state='MA',center=[-71.11,42.372],zoom=12)}
BY_CITY={c['name']:k for k,c in CITIES.items()}
geocodes={}
gfile=PACK/'data/census-results.csv'
if gfile.exists():
 for row in csv.reader(gfile.open()):
  if len(row)>=3 and row[0].startswith('A'):
   entry={'status':row[2],'match_type':row[3] if len(row)>3 else '', 'matched_address':row[4] if len(row)>4 else '', 'provider':'US Census Geocoder · Public_AR_Current','queried_at':'2026-10-03','coordinate_note':'Interpolated address-range match; not a parcel boundary or jurisdiction determination.'}
   if row[2]=='Match':
    try:
     xy=[float(v) for v in row[5].split(',')]
     if len(xy)==2 and -180<=xy[0]<=180 and -90<=xy[1]<=90:entry['coordinates']=xy
    except ValueError:pass
   geocodes[row[0]]=entry
properties=[]
for r in csv.DictReader((PACK/'data/sample_addresses.csv').open()):
 city=BY_CITY.get(r['postal_city'])
 if city is None:city='boston' if r['source_dataset'].startswith('Boston') else 'sd' if r['source_dataset'].startswith('SANDAG') else None
 assert city, r
 g=geocodes.get(r['address_id'],{'status':'Not geocoded'})
 if g.get('coordinates') and f", {r['state']}," not in g.get('matched_address',''):
  g={**g,'status':'Needs review','coordinates':None}
 properties.append({**r,'id':r['address_id'],'city':city,'address':r['street_address'],'year':int(r['year_built']) if r['year_built'] else None,'units':int(float(r['units'])) if r['units'] else None,'geocode':g,'coord':g.get('coordinates'),'jurisdiction_status':'Unresolved','owner_type':None})
sources=load_sources(ROOT)
check_rule_sources(sources,json.loads((ROOT.parent/'out/rules.json').read_text())['rules'])
write_sources(sources,OUT)
S={s['doc_id']:s for s in sources}
readings=[]
def add(doc,cat,title,value,needle,summary,needs,date=None,end=None,temporal='snapshot',length=650,date_basis=None):
 s=S[doc];text=s['text'];assert text, doc
 pattern=r'\s+'.join(re.escape(w) for w in needle.split())
 m=re.search(pattern,text,re.I)
 assert m,(doc,needle)
 stop=min(len(text),m.start()+length)
 stop=max(m.end(),text.rfind(' ',m.end(),stop))
 quote=text[m.start():stop]
 assert quote in text
 readings.append(dict(id=doc+'-'+cat,doc_id=doc,cat=cat,title=title,value=value,quote=quote,summary=summary,needs=needs,effective_date=date,end_date=end,temporal=temporal,jurisdiction=s['jurisdictions'],method='Curated source reading; not automated extraction',date_basis=date_basis or ('Participant change test' if temporal=='test' else 'Supplied source snapshot')))
add('D080','rent','San Francisco annual adjustment','1.6% annual allowable increase','For rent-controlled units, the annual allowable increase amount','The captured Rent Board announcement gives a 1.6% adjustment for covered units from March 1, 2026 through February 28, 2027.','Confirm rent-control coverage, occupancy certificate, tenancy details, and applicable exceptions.','2026-03-01','2027-02-28',length=520)
add('D024','rent','California statewide rent cap','5% + cost of living, capped at 10%','Subject to subdivision (b), an owner of residential real property','The statute describes a 12-month cap and lists exclusions, including certain newer housing and housing under a stricter local cap.','Occupancy certificate, exemptions, tenancy facts, and local-rule precedence are unresolved.',length=900)
add('D025','deposit','California security deposits','General limit: one month’s rent','Except as provided in paragraph (2), (3), or (5), a landlord','The general limit has exceptions. The small-landlord exception depends on ownership and total rental units, which the sample does not fully establish.','Confirm applicable exceptions and tenancy dates. Owner type and portfolio size are absent.',length=600)
add('D026','fee','California screening fees','Actual costs, subject to an indexed cap','The amount of the application screening fee shall not be greater','The statute limits actual screening costs and permits annual CPI adjustment of a base amount. The pack does not establish a single verified current dollar cap.','Current CPI calculation, unit availability, screening process, and refund conditions require review.',length=800)
add('D023','shield','California just-cause protections','Tenancy conditions and exemptions matter','the owner of the residential real property shall not terminate a tenancy without just cause','The statute ties eviction protections to occupancy duration and other conditions. Building age alone does not decide coverage.','Tenancy duration, exempt status, occupancy certificate, and the asserted cause are missing.',length=600)
add('D027','screen','California housing discrimination protections','Source of income is a protected ground','source of income, disability, veteran','The captured statute addresses housing discrimination, including source of income. This preview does not determine whether a particular practice violates it.','Review the relevant subsection, exemptions, and conduct; these facts are not in assessor records.',length=380)
add('D022','algorithm','California common pricing algorithms','Restrictions on common pricing algorithms','This bill would also make it unlawful','The supplied bill page describes the restriction; test T1 specifies the January 1, 2026 transition. Source text and test expectations are kept separate.','Legal interpretation and property-specific conduct have not been evaluated.','2026-01-01',temporal='test',length=750)
add('D079','shield','San Francisco just-cause overview','A just-cause reason for covered units','In order to evict a tenant','The Rent Board overview explains just-cause requirements for units covered by the Rent Ordinance.','Coverage, tenancy history, exemptions, and the reason for termination need review.',length=520)
add('D081','algorithm','San Francisco algorithmic devices','Local restriction on algorithmic devices','Legislation\nadding Section 37.10C','The city announcement describes a local restriction effective October 14, 2024, separate from the later state change.','Confirm city jurisdiction and the definition of the software or conduct involved.','2024-10-14',length=750)
add('D008','rent','Berkeley 2026 annual adjustment','1.0% adjustment for eligible landlords','At its regular meeting on October 16, 2025','The captured notice gives a 1.0% adjustment and additional eligibility and tenancy conditions.','Year built and unit count are absent for every Berkeley sample; tenancy and coverage facts are also needed.','2026-01-01','2026-12-31',length=850)
add('D041','rent','Los Angeles rent stabilization','Coverage depends on building and tenancy','Generally, the RSO applies','The housing department describes building-date tests and covered property types.','Confirm occupancy date, unit eligibility, exemptions, and legal city. The construction year is only a recorded fact.',length=650)
add('D040','shield','Los Angeles just-cause ordinance','Termination and relocation requirements','It prohibits terminations of tenancies without just cause','The city explains protections and relocation assistance for covered rental units.','Confirm ordinance coverage, tenancy duration, exemptions, and termination circumstances.',length=600)
add('D073','shield','San Diego tenant protections','Just cause and relocation assistance','This\nDivision protects the rights of tenants','The municipal text describes just-cause requirements and additional tenant protections.','Confirm legal jurisdiction, exemptions, and tenancy facts. Construction years are absent in this city’s sample.',length=650)
add('D066','fee','New Jersey application fee limit','$50 maximum application fee','A landlord, or agent thereof, shall not require an application','The captured law limits residential rental application fees. The participant guide places its effective date at May 1, 2026.','Confirm the transaction falls within the statute. The assessor dataset contains no fees charged.','2026-05-01',temporal='test',length=540,date_basis='Participant guide (effective date); captured statute (fee limit)')
add('D065','screen','New Jersey Fair Chance in Housing','Criminal-history screening restrictions','prior to the provision of a conditional offer','The law restricts screening before a conditional offer and contains specified exceptions.','Housing-provider coverage, application stage, and exceptions require review.',length=650)
add('D069','algorithm','New Jersey FAIR Act','Enacted; future effective date','This act shall be known and may be cited','The supplied act is accompanied by test T3, which specifies July 1, 2027 and a possible conflict with Jersey City and Hoboken rules.','State/local interaction requires human review. No property-level legal determination has run.','2027-07-01',temporal='test',length=410)
add('D052','deposit','Massachusetts security deposits','Deposit equal to the first month’s rent','a security deposit equal to the first month','The statute describes the deposit limit together with handling and statement-of-condition requirements.','Confirm tenancy context and exceptions. The sample contains neither rent nor deposits paid.',length=650)
add('D052','fee','Massachusetts upfront charges','Specified categories of upfront payment','No lessor may require a tenant or prospective tenant','The statute restricts upfront charges; its text includes versions with different effective dates.','Select the correct statutory version and review the specific charges and tenancy date.',length=600)
add('D048','rent','Massachusetts rent-control restrictions','General prohibition with a stated exception','No city or town may enact','The statute limits local rent control and describes an exception. Test T5 separately requires no cap from the failed ballot proposal.','Do not infer an active cap from a proposal or omit the statutory exception.',length=700)
add('D045','algorithm','Massachusetts H.5222','Pending bill in the supplied snapshot','Status:\nReferred to House Committee','The supplied bill page shows referral to Ways and Means. Pending status is a snapshot, not a prediction of later passage.','No obligation is inferred from this pending proposal.',temporal='pending',length=420)
add('D046','algorithm','Massachusetts S.2983','Pending bill in the supplied snapshot','Status:\nReferred to Senate Committee','The supplied bill page shows referral to Ways and Means. Test T4 asks for potential reach if enacted.','No obligation is inferred from this pending proposal.',temporal='pending',length=420)
add('D031','shield','Cambridge tenant-rights notification','Information at the start and end of tenancy','The Ordinance requires owners, landlords, and management companies','The municipal page describes notification duties. This is not a claim of just-cause eviction coverage.','Confirm legal city, tenancy event, and current ordinance version.',length=500)
audit=json.loads((PACK/'data-audit.json').read_text())
data=dict(snapshot='2026-10-01',cities=CITIES,properties=properties,sources=sources,readings=readings,change_tests=json.loads((PACK/'dev/change_tests.json').read_text()),audit=audit,geocoded=sum(bool(p['coord']) for p in properties))
write_starter(data,OUT)
print(f"Built {len(properties)} properties, {len(sources)} source records, {len(readings)} exact-span readings, {data['geocoded']} geocoded addresses.")

import sys
REPO=ROOT.parent
OUTP=REPO/'out'
DATES=['2025-12-31','2026-01-02','2026-10-01','2027-07-02']
buildings=json.loads((OUTP/'buildings.json').read_text())
rules_doc=json.loads((OUTP/'rules.json').read_text())
rules=rules_doc['rules']
no_rule_findings=rules_doc.get('no_rule_findings',[])
base=json.loads((OUTP/'lookups.json').read_text())
detail=json.loads((OUTP/'lookups_detail.json').read_text())
changes=json.loads((OUTP/'changes.json').read_text())
run=json.loads((OUTP/'engine_run.json').read_text())
t6_rehearsal=json.loads((REPO/'engine/fixtures/t6_rehearsal.json').read_text())
inferred_omissions=json.loads((OUTP/'inferred_omissions.json').read_text()) if (OUTP/'inferred_omissions.json').exists() else None
retrieved={}
for mf in [PACK/'corpus/corpus_manifest.csv',REPO/'corpus_extra/manifest_extra.csv']:
 if mf.exists():
  for d in csv.DictReader(mf.open()):retrieved[d['doc_id']]=d.get('retrieved_at') or None
sys.path.insert(0,str(REPO))
from engine.run import evaluation_rules, presented_lookups
from engine.temporal import build_rule_timeline
erules=evaluation_rules()
annotations={r['team_rule_id']:r.get('_annotation') or {} for r in erules}
erules_by_id={r['team_rule_id']:r for r in erules}
by_date={}
for d in DATES:
 by_date[d]=presented_lookups(buildings,erules,d)[0]
by_date[base['as_of']]=base['lookups']
texts=[];tidx={}
def T(x):
 if x not in tidx:tidx[x]=len(texts);texts.append(x)
 return tidx[x]
lookups={d:{a:[[e['team_rule_id'],e['result'],T(e['explanation']),int(bool(e.get('conflict_flag')))] for e in es] for a,es in L.items()} for d,L in sorted(by_date.items())}
keep=['team_rule_id','jurisdiction','level','category','status','title','requirement','key_value','exemptions','effective_date','citation','source_doc_id','source_url','quoted_span','confidence','conflict_flag','conflict_note','plain_language','coverage_conditions','coverage','verification','found_by','source_note','source_notes']
def subsidized_program(rid):
 erule=erules_by_id.get(rid,{})
 conditions=erule.get('_conditions') or []
 classified=any(c.get('nature')=='positive_limit' and (c.get('affordable_targeted') or
  re.search(r'\b(subsidi[sz]ed|affordable|income[- ]restricted|IDP|DND)\b',
            ' '.join(str(c.get(k) or '') for k in ('label','text')),re.I)) for c in conditions)
 summary=str((erule.get('coverage_conditions') or {}).get('summary') or '')
 v3_positive=bool(re.match(r'\s*applies only\b',summary,re.I) and
                  re.search(r'\b(subsidi[sz]ed|affordable|income[- ]restricted|IDP|DND)\b',summary,re.I))
 return classified or v3_positive
rules_ui={r['team_rule_id']:{**{k:r.get(k) for k in keep},
 'retrieved_at':retrieved.get(r.get('source_doc_id')),
 'source_type':(S.get(r.get('source_doc_id')) or {}).get('source_type'),
 'source_capture':bool(str(r.get('source_doc_id') or '').startswith('DX')),
 'event_only':bool(r.get('event_only') or (annotations.get(r['team_rule_id']) or {}).get('event_only')),
 'subsidized_program':bool(subsidized_program(r['team_rule_id']))} for r in rules}
def fact_hint(rule, missing):
 cc=rule.get('coverage_conditions') or {}; cov=rule.get('coverage') or {}
 cutoff=cov.get('construction_cutoff') or {}
 if not cutoff and cc.get('built_on_or_before'):
  cutoff={'covered_if':'on_or_before','date':cc['built_on_or_before'],'basis':cc.get('construction_date_basis') or 'construction date'}
 if not cutoff and cc.get('built_after'):
  cutoff={'covered_if':'after','date':cc['built_after'],'basis':cc.get('construction_date_basis') or 'construction date'}
 if any('year' in f or 'construction' in f or 'occupancy' in f for f in missing):
  if cutoff.get('date'):
   op={'on_or_before':'on or before','after':'after','before':'before','on_or_after':'on or after'}.get(cutoff.get('covered_if'),cutoff.get('covered_if'))
   return {'fact':'year_built','condition':f"Coverage requires {cutoff.get('basis') or 'construction date'} {op} {cutoff['date']}."}
  nc=cov.get('new_construction_exemption') or {}
  years=nc.get('years') or cc.get('min_building_age_years')
  if years:return {'fact':'year_built','condition':f"Housing less than {years} years old is exempt; enter the construction year to test the rolling cutoff."}
 if any('unit' in f for f in missing):
  lo=cov.get('min_units') if cov.get('min_units') is not None else cc.get('min_units')
  hi=cov.get('max_units') if cov.get('max_units') is not None else cc.get('max_units')
  if lo is not None:return {'fact':'units','condition':f"Coverage requires at least {lo} units."}
  if hi is not None:return {'fact':'units','condition':f"Coverage is limited to buildings with at most {hi} units."}
 return None

details_ui={aid:{rid:{'summary':d.get('summary'),'reasoning':d.get('reasoning'),'missing_facts':d.get('missing_facts',[]),'confidence':d.get('confidence'),
 'needs_review':bool(d.get('needs_review')),'fact_hint':fact_hint(erules_by_id.get(rid,{}),d.get('missing_facts',[]))} for rid,d in row.get('rules',{}).items()}
 for aid,row in detail.get('addresses',{}).items()}
bkeep=['address_id','state','legal_city','legal_city_candidate','city_status','place_geoid','county','year_built','units','units_min','property_type','use_description','missing_facts','threshold_year_case','input_address','postal_city','zip','geocode_status','jurisdiction_mismatch','unincorporated','flags']
bkeep += ['units_max','units_method','city_confidence','year_built_max','year_built_max_method','co_date_min','co_date_max','co_date_method','subsidized','subsidized_source','elderly_housing','elderly_housing_source','tenancy_in_common','tenancy_in_common_source']
scheduled_changes={}
for aid,b in sorted(buildings.items()):
 future=build_rule_timeline(b,erules,base['as_of'],'2028-12-31')[1:]
 if future:scheduled_changes[aid]=future
eng=dict(default_date=base['as_of'],dates=sorted(by_date),rules_sha256=run.get('rules_sha256'),rule_count=run.get('rule_count'),rules_evaluated=run.get('rules_evaluated'),excluded=run.get('excluded',[]),
 buildings={a:{k:b.get(k) for k in bkeep} for a,b in buildings.items()},rules=rules_ui,texts=texts,lookups=lookups,
 details=details_ui,no_rule_findings=no_rule_findings,scheduled_changes=scheduled_changes,
 changes={t:v for t,v in changes.items() if t!='_meta'},
 t6_rehearsal=t6_rehearsal,inferred_omissions=inferred_omissions,
 acceptance={'selfcheck':'17/17','fixed_change_tests':'T1-T5','rules_sha256':run.get('rules_sha256')},
 version={'git_sha':os.environ.get('PARCEL_BUILD_SHA') or None,'rules_sha256':hashlib.sha256((OUTP/'rules.json').read_bytes()).hexdigest(),
  'generated_at':os.environ.get('PARCEL_BUILD_DATE') or None})
(OUT/'engine-data.js').write_text('window.ENGINE_DATA = '+json.dumps(eng,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')+';\n')
print(f"Engine data: {len(buildings)} buildings, {len(rules)} rules, dates {', '.join(eng['dates'])}, {len(texts)} distinct explanations.")
