# -*- coding: utf-8 -*-
r"""Разложить 2 577 паспортов с чужими источниками по правилу владельца.

Правило (04.09): если паспорт и контакты собраны с ОДНОГО сайта — пусть даже
чужого этой компании, — такой паспорт не выкидываем: письмо и адресат сходятся
между собой. Выкидываем только СМЕСЬ, где к своим страницам подмешана чужая:
там факты приехали со страницы, к адресату отношения не имеющей.

Ничего не меняем — только считаем и складываем списки.
"""
import json, os, re, sqlite3
def дом(с):
    d = re.sub(r'^https?://', '', str(с or '').strip().lower()).split('/')[0]
    return d[4:] if d.startswith('www.') else d
def родня(a, b):
    return bool(a) and bool(b) and (a == b or a.endswith('.' + b) or b.endswith('.' + a))
c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=600)
почты = {}
for инн, e, u in c.execute("select inn, lower(email), coalesce(source_url,'') from emails"):
    почты.setdefault(str(инн), []).append((e, u))
итог = {'смесь_своё_и_чужое': 0, 'один_чужой_и_контакты_оттуда': 0,
        'один_чужой_но_контактов_оттуда_нет': 0, 'много_чужих_доменов': 0}
на_пересбор, оставить = [], []
for инн, сайт, сырое, div in c.execute(
        "select f.inn, coalesce(f.site,''), coalesce(f.sources_json,''), "
        "coalesce(k.division,'') from site_facts f join companies k on k.inn=f.inn "
        "where coalesce(f.facts_json,'')<>''"):
    try:
        источники = json.loads(сырое or '[]')
    except Exception:                                          # noqa: BLE001
        continue
    if not isinstance(источники, list) or not источники:
        continue
    свой = дом(сайт)
    if not свой:
        continue
    чужие = [u for u in источники if not родня(дом(u), свой)]
    if not чужие:
        continue
    инн = str(инн)
    домены_чужих = {дом(u) for u in чужие}
    свои_есть = len(чужие) < len(источники)
    if свои_есть:
        итог['смесь_своё_и_чужое'] += 1
        на_пересбор.append([инн, свой, sorted(домены_чужих)[:2], div])
    elif len(домены_чужих) == 1:
        д = next(iter(домены_чужих))
        оттуда = any(родня(дом(u), д) or родня(e.split('@')[-1], д)
                     for e, u in почты.get(инн, []))
        if оттуда:
            итог['один_чужой_и_контакты_оттуда'] += 1
            оставить.append([инн, свой, д, div])
        else:
            итог['один_чужой_но_контактов_оттуда_нет'] += 1
            на_пересбор.append([инн, свой, [д], div])
    else:
        итог['много_чужих_доменов'] += 1
        на_пересбор.append([инн, свой, sorted(домены_чужих)[:2], div])
c.close()
итог['ИТОГО_на_пересбор'] = len(на_пересбор)
итог['ИТОГО_оставить'] = len(оставить)
итог['на_пересбор_мейер'] = sum(1 for x in на_пересбор if 'meyer' in (x[3] or '').lower())
for имя, данные in (('pasporta-na-peresbor.jsonl', на_пересбор),
                    ('pasporta-ostavit.jsonl', оставить)):
    п = os.path.join(r'C:\sender\server', имя)
    with open(п, 'w', encoding='utf-8') as f:
        for x in данные:
            f.write(json.dumps({'inn': x[0], 'сайт': x[1], 'чужие': x[2],
                                'направление': x[3]}, ensure_ascii=False) + '\n')
        f.flush(); os.fsync(f.fileno())
итог['примеры_оставить'] = оставить[:4]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2500])
