import sys, json, requests
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
requests.packages.urllib3.disable_warnings()
L=[json.loads(l) for l in open(r'C:\sender\_ops\ak\torgi-lenta.jsonl',encoding='utf-8')]
ids=[x['id'] for d in L for x in d['lots']]
print('лотов', len(ids))
for lid in ids[:2]:
    j=requests.get(f'https://torgi.gov.ru/new/api/public/lotcards/{lid}', headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'}, timeout=60, verify=False).json()
    print('== ключи:', sorted(j.keys())[:60])
    s=json.dumps(j, ensure_ascii=False)
    print('   lotName:', j.get('lotName')); print('   attrs:', [ (a.get('fullName') or a.get('name'), str(a.get('value'))[:60]) for a in (j.get('attributes') or [])][:12])
    for k in ('bidderOrg','organizerOrg','ownerInfo','debtorInfo','rightHolderInfo','organization','seller','ownerOrganization'):
        if k in j: print('  ', k, ':', json.dumps(j[k], ensure_ascii=False)[:300])
    import re
    print('   контексты ИНН:', [s[max(0,m.start()-80):m.end()+20] for m in re.finditer(r'\d{10}', s)][:4])
