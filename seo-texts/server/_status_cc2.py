import glob, io, json, os, subprocess
DIR = r'C:\sender\server'
o = {}
for имя, маска in (('cc-opisanie.jsonl', 'cc_opisanie_*.log'), ('cc-checko.jsonl', 'cc_checko_*.log')):
    п = os.path.join(DIR, имя)
    стр = [json.loads(s) for s in io.open(п, encoding='utf-8', errors='replace')] if os.path.exists(п) else []
    o[имя] = len(стр)
    if имя == 'cc-checko.jsonl' and стр:
        o['checko_пример'] = [{k: str(v)[:120] for k, v in з.items() if k in ('inn', 'ogrn', 'okved_main', 'okveds_all', 'выручка_руб', 'выручка_год', 'выручка_фрагмент', 'выручка_страница', 'dd_err', 'ошибка')} for з in стр[:3]]
        o['с_окведами'] = sum(1 for з in стр if з.get('okveds_all'))
        o['с_выручкой'] = sum(1 for з in стр if з.get('выручка_руб'))
    if имя == 'cc-opisanie.jsonl' and стр:
        o['opis_пример'] = [{k: str(v)[:150] for k, v in з.items() if k in ('домен', 'описание', 'целевая', 'сегмент', 'почему', 'итог')} for з in стр[:3]]
    логи = sorted(glob.glob(os.path.join(DIR, маска)), key=os.path.getmtime)
    if логи:
        o[имя + ' лог'] = io.open(логи[-1], encoding='utf-8', errors='replace').read()[-250:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
