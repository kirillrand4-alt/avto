# -*- coding: utf-8 -*-
import io, json, sys, time
sys.path.insert(0, r'C:\sender\server')
import poisk_razbor as PR
import cc_obhod as CO
serp = [json.loads(s) for s in io.open(r'C:\sender\server\poisk-serp.jsonl', encoding='utf-8', errors='replace')]
сайты, кат = [], []
for з in serp[40:80]:
    for д in з['доки'][:6]:
        h = PR.хост(д['url'])
        if PR.НЕ_БРАТЬ.search(h):
            continue
        (кат if PR.КАТАЛОГ.search(h) or not PR.EC._is_own_site('http://' + h) else сайты).append((h, д['url']))
t = time.time()
база = CO.домены_базы()
имена = PR.индекс_имён()
o = {'серп_строк': len(serp), 'сайтов_в_выборке': len(сайты), 'каталогов': len(кат)}
o['сайты'] = []
for h, u in сайты[:8]:
    з = PR.сайт(h, {'url': u}, база, имена)
    o['сайты'].append([h, з['страниц'], з['инн'][:2], з['инн_база'][:2], з['инн_по_имени'][:2], з['юримена'][:2]])
o['каталоги'] = []
for _h, u in кат[:0]:
    з = PR.каталог(u)
    o['каталоги'].append([u[:60], з['страница'], з['инн_url'], len(з.get('инн', [])), len(з.get('огрн', []))])
o['сек'] = round(time.time() - t)
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=0)[:5000])
