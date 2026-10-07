import glob, io, json, os
DIR = r'C:\sender\server'
п = os.path.join(DIR, 'cc-checko-proxy.jsonl')
стр = [json.loads(s) for s in io.open(п, encoding='utf-8', errors='replace')] if os.path.exists(п) else []
o = {'строк': len(стр), 'ok': sum(1 for з in стр if з.get('итог') == 'ok'),
     'с_доп_оквэд': sum(1 for з in стр if len(з.get('оквэд_все') or []) > 1),
     'с_выручкой': sum(1 for з in стр if з.get('выручка')),
     'коды_ответов': {}, 'пример': [{k: str(v)[:100] for k, v in з.items()} for з in стр[:3]]}
for з in стр:
    for к in ('activity', 'company'):
        if к in з:
            o['коды_ответов'][str(з[к])] = o['коды_ответов'].get(str(з[к]), 0) + 1
логи = sorted(glob.glob(os.path.join(DIR, 'cc_checko_proxy_*.log')), key=os.path.getmtime)
if логи:
    o['лог'] = io.open(логи[-1], encoding='utf-8', errors='replace').read()[-300:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
