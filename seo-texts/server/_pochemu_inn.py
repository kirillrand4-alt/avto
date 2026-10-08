import io, json, os, sys, re
sys.path.insert(0, r'C:\sender\server')
os.environ['KC_NABOR'] = 'poisk'
ИНН = ['1832104677', '1821009492']
o = {}
for i in ИНН:
    з = {}
    з['в_разборе'] = [ (x.get('тип'), x.get('домен') or x.get('url'), x.get('инн'), x.get('инн_база'), x.get('инн_по_имени'))
                     for x in (json.loads(s) for s in io.open(r'C:\sender\server\poisk-razbor.jsonl', encoding='utf-8', errors='replace'))
                     if i in json.dumps(x)][:6]
    сп = json.load(io.open(r'C:\sender\server\poisk-spisok.json', encoding='utf-8'))
    з['в_списке'] = [k for k in ('компании', 'снято', 'ниже_порога', 'на_решение') if i in сп[k]]
    for k in з['в_списке']:
        з['запись'] = {kk: сп[k][i].get(kk) for kk in ('имя', 'осн', 'сегм', 'выручка', 'сайт', 'откуда', 'причина')}
    import poisk_otbor as PO
    з['доход_фнс'] = PO.доходы({i}).get(i)
    з['наши'] = {k: v for k, v in (PO.наши_данные({i}).get(i) or {}).items() if k in ('имя', 'осн', 'регион', 'статус', 'сайт')}
    o[i] = з
print('===ИТОГ==='); print(json.dumps(o, ensure_ascii=False, indent=1, default=str)[:5000])
