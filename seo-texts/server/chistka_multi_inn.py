# -*- coding: utf-8 -*-
r"""Мульти-ИНН домены: механика + реквизиты, спорных — в очередь приговора.

Запуск владельца 17.08 («запускай 1,2,3») по находке соседа: 2802 домена
привязаны к нескольким ИНН, под ними 7729 карточек. Лестница решений:

  A. Домен из списка площадок (tenderguru, myseldon, my-gkh...) — справочник:
     снять ВСЁ (site и cand_site), паспорта в карантин. Реквизиты на каталоге
     уликой не считаются: каталог печатает ИНН каждой компании by design.
  B. Домен на 3+ ИНН не из списка:
     кандидаты (cand_site) — снять: заслон в poisk_saytov найдёт заново честно;
     живые привязки — если страницы похожи на каталог (много чужих ИНН) снять;
     если на страницах РЕКВИЗИТЫ компании (ИНН/ОГРН — не «имя» и не «домен»,
     это ловушка тёзок: у всех «Векторов» имя читается в avtoschool-vektor.ru)
     — оставить; остальные — В ОЧЕРЕДЬ ПРИГОВОРА модели (там и филиалы
     ЕвроХима на сайте холдинга, и тёзки-прилипалы — различит только контент).
  C. Домен ровно на 2 ИНН: живые привязки так же — реквизиты или очередь;
     кандидатов не трогаем (безвредны до промоции, промоцию держит заслон).

Снятое пишется durable: enrich.db (site_facts.otkloneno_json) + jsonl с fsync.
Очередь приговора — prigovor-ochered.jsonl, судит prigovor_domenov.py.

    python chistka_multi_inn.py            посчитать, ничего не трогая
    python chistka_multi_inn.py --primenit применить
"""
import gzip
import json
import os
import re
import sqlite3
import sys
import time
from collections import defaultdict

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender\server', r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import ploshchadki as PL          # noqa: E402
import sverka_privyazki as SP     # noqa: E402

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
ЛОГ = os.path.join(DIR, 'chistka_multi_inn.jsonl')
ОЧЕРЕДЬ = os.path.join(DIR, 'prigovor-ochered.jsonl')


def собрать():
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    по_домену = defaultdict(list)
    for r in c.execute(
            "select inn, coalesce(name,'') name, coalesce(ogrn,'') ogrn, "
            "coalesce(region,'') region, coalesce(okved,'') okved, "
            "coalesce(nullif(site,''),'') s, coalesce(nullif(cand_site,''),'') cs "
            'from companies'):
        for поле, знач in (('site', r['s']), ('cand_site', r['cs'])):
            д = PL.домен(знач) if знач else ''
            if д:
                по_домену[д].append({'inn': str(r['inn']), 'name': r['name'],
                                     'ogrn': r['ogrn'], 'region': r['region'],
                                     'okved': r['okved'], 'поле': поле})
    c.close()
    return {д: сп for д, сп in по_домену.items()
            if len({x['inn'] for x in сп}) >= 2}


def _текст(inn):
    p = os.path.join(KESH, '%s.json.gz' % inn)
    if not os.path.exists(p):
        return ''
    try:
        d = json.loads(gzip.open(p, 'rb').read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        return ''
    куски = []
    for pg in (d.get('pages') or []):
        h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ',
                   pg.get('html') or '', flags=re.S | re.I)
        куски.append(re.sub(r'<[^>]+>', ' ', h))
    return re.sub(r'\s+', ' ', ' '.join(куски).lower().replace('ё', 'е'))


def разложить():
    """Каждой привязке — решение: снять / оставить / приговор."""
    цели = собрать()
    решения = []
    for д, сп in sorted(цели.items()):
        инны = {x['inn'] for x in сп}
        каталог = bool(PL.из_списка('http://' + д))
        for x in сп:
            куда, почему = '', ''
            if каталог:
                куда = 'снять'
                почему = 'домен из списка площадок'
            elif x['поле'] == 'cand_site':
                if len(инны) >= 3:
                    куда, почему = 'снять', 'кандидат на домене %d юрлиц' % len(инны)
                else:
                    куда, почему = 'оставить', 'кандидат, решит заслон при промоции'
            else:
                т = _текст(x['inn'])
                if not т:
                    куда, почему = 'приговор', 'страниц в кэше нет'
                elif PL.много_чужих_инн(т, x['inn']):
                    куда, почему = 'снять', 'на страницах много чужих ИНН — каталог'
                else:
                    ул, _ = SP.улики(x['inn'], x['name'], д, x['ogrn'], текст=т)
                    рекв = [u for u in ул if u in ('инн', 'огрн')]
                    if рекв:
                        куда, почему = 'оставить', 'реквизиты на страницах: ' + ','.join(рекв)
                    else:
                        куда, почему = 'приговор', 'без реквизитов, решает модель'
            решения.append({**{k: x[k] for k in ('inn', 'name', 'region',
                                                 'okved', 'поле')},
                            'домен': д, 'юрлиц_на_домене': len(инны),
                            'куда': куда, 'почему': почему})
    return решения


def свод(решения):
    из = {'привязок_разобрано': len(решения)}
    for р in решения:
        к = '%s_%s' % (р['куда'], р['поле'])
        из[к] = из.get(к, 0) + 1
    из['в_очередь_приговора'] = sum(1 for р in решения if р['куда'] == 'приговор')
    return из


def применить():
    решения = разложить()
    c = sqlite3.connect(BD, timeout=120)
    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    снято = карантин = 0
    for р in решения:
        if р['куда'] != 'снять':
            continue
        n = c.execute(
            'UPDATE companies SET %s=NULL, updated_at=? WHERE inn=? '
            'AND coalesce(%s,\'\') LIKE ?' % (р['поле'], р['поле']),
            (ts, р['inn'], '%' + р['домен'] + '%')).rowcount
        снято += n
        if р['поле'] == 'site' and n:
            карантин += c.execute(
                "UPDATE site_facts SET otkloneno_json=facts_json, facts_json='', "
                'privyazka=?, note=? WHERE inn=? AND coalesce(facts_json,\'\')<>\'\'',
                ('мульти-ИНН: ' + р['домен'],
                 '%s (юрлиц на домене: %d)' % (р['почему'], р['юрлиц_на_домене']),
                 р['inn'])).rowcount
    c.commit()
    c.close()
    with open(ЛОГ, 'a', encoding='utf-8') as f:
        for р in решения:
            if р['куда'] == 'снять':
                f.write(json.dumps({**р, 'ts': ts}, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    # очередь приговора — с перезаписью: судья читает и пропускает уже судимых
    with open(ОЧЕРЕДЬ, 'w', encoding='utf-8') as f:
        for р in решения:
            if р['куда'] == 'приговор':
                f.write(json.dumps(р, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return {**свод(решения), 'снято_строк': снято, 'паспортов_в_карантин': карантин}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if '--primenit' in sys.argv:
        print(json.dumps(применить(), ensure_ascii=False, indent=1))
    else:
        решения = разложить()
        примеры = defaultdict(list)
        for р in решения:
            if len(примеры[р['куда']]) < 5:
                примеры[р['куда']].append(
                    {k: р[k] for k in ('домен', 'name', 'поле', 'почему')})
        print(json.dumps({'примеры': dict(примеры)}, ensure_ascii=False, indent=1))
        print(json.dumps(свод(решения), ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
