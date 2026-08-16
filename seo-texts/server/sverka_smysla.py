# -*- coding: utf-8 -*-
r"""Сверка СМЫСЛА: тот ли бизнес на сайте, что у компании в базе.

Откуда. Владелец 16.08 смотрел 20 паспортов глазами и нашёл ООО «Группа "Баренц"»
(по ЕГРЮЛ переработка рыбы), у которого сайт barenz.group продаёт квартиры в
Петрозаводске. Ни ИНН, ни имя такую привязку не выдают — домен как раз собран из
названия. Вопрос владельца: сколько таких.

ГЛАВНАЯ ОГОВОРКА, без неё замер врёт. Расхождение с ОКВЭД само по себе НЕ улика:
на том и стоит весь проект — «Пивкомбинат Балаковский» по сайту делает печенье и
пряники, а не пиво, и это правда сайта, а не ошибка привязки. Поэтому судья
получает ОКВЭД как справку, а не как истину, и обязан отдельно ответить, есть ли
у него улики ПРИНАДЛЕЖНОСТИ сайта, помимо совпадения тематики.

Раскладка на три корзины:
    свой        — есть улика принадлежности (ИНН/ОГРН/имя/домен), бизнес не спорит;
    расходится  — улика есть, но бизнес на сайте другой: холдинг, второе
                  направление, смена деятельности. Письму такое не мешает —
                  паспорт описывает то, что компания делает СЕЙЧАС;
    чужой       — улик нет ИЛИ судья видит прямое противоречие без объяснения.
                  Вот это и есть цена вопроса.

    python sverka_smysla.py --zamer [N]     замер на выборке (по умолчанию 400)
    python sverka_smysla.py --vse           пройти все паспорта, резюмируемо
    python sverka_smysla.py --stat          что уже насчитано
"""
import json
import os
import random
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import sverka_privyazki as SP     # noqa: E402
import ploshchadki as PL          # noqa: E402

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
MODEL = os.environ.get('SMYSL_MODEL', 'claude-haiku-4-5')
ОТВЕТЫ = os.path.join(DIR, 'sverka_smysla.jsonl')

PROMPT = """Ты проверяешь, принадлежит ли сайт именно этой компании.

Компания по государственному реестру:
  название: %(name)s
  ИНН: %(inn)s
  ОКВЭД: %(okved)s

Сайт: %(site)s
Что на сайте (собрано из текста его страниц):
  продукция и услуги: %(produkciya)s
  цитата со страницы: %(citata)s
  клиенты: %(klienty)s

ВАЖНО. ОКВЭД — это справка, а не истина. Компания сплошь и рядом делает не то, что
записано кодом: «Пивкомбинат» выпускает печенье, «Молзавод» — мороженое. Само по
себе расхождение ОКВЭД и сайта НИЧЕГО не доказывает и поводом для вердикта «чужой»
быть не может.

Признаки того, что сайт ЧУЖОЙ, — только такие:
  * сайт принадлежит другой организации, названной на нём прямо;
  * это витрина маркетплейса, справочник, реестр, новостной портал, а не сайт
    предприятия;
  * бизнес на сайте не мог бы вестись этим юрлицом ни при каком развитии событий
    (например, микропредприятие-грузоперевозчик, а сайт — федеральный банк).

Верни СТРОГО JSON:
{"verdikt": "свой|расходится|чужой",
 "uverennost": "высокая|средняя|низкая",
 "prichina": "одна фраза, по делу"}

«расходится» ставь, когда сайт похож на сайт ЭТОЙ компании (имя, домен), но
занятие другое, чем в ОКВЭД: это нормальная жизнь бизнеса, а не ошибка.
"""


def _спискок(v, n=8):
    if isinstance(v, list):
        return '; '.join(str(x)[:60] for x in v[:n]) or '(пусто)'
    return (str(v)[:200] if v else '(пусто)')


def задачи(предел=0, только_без_жёстких_улик=True):
    """Паспорта, по которым имеет смысл спрашивать судью."""
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    строки = list(c.execute(
        "select f.inn, f.facts_json, coalesce(f.site,'') site, coalesce(k.name,'') name, "
        "coalesce(k.okved,'') okved, coalesce(k.ogrn,'') ogrn "
        "from site_facts f join companies k on k.inn=f.inn "
        "where coalesce(f.facts_json,'')<>'' and coalesce(f.format,0)>=2"))
    c.close()
    готовые = set()
    if os.path.exists(ОТВЕТЫ):
        with open(ОТВЕТЫ, encoding='utf-8') as f:
            for s in f:
                try:
                    готовые.add(json.loads(s)['inn'])
                except Exception:  # noqa: BLE001
                    pass
    из = []
    for r in строки:
        inn = str(r['inn'])
        if inn in готовые:
            continue
        d = {}
        try:
            d = json.loads(r['facts_json'])
        except Exception:  # noqa: BLE001
            continue
        найдено, _ = SP.улики(inn, r['name'], r['site'], r['ogrn'])
        # ИНН и ОГРН на странице — улика жёсткая; спрашивать судью незачем, кроме
        # случая, когда сама страница оказалась площадкой (там ИНН печатают все)
        if только_без_жёстких_улик and ('инн' in найдено or 'огрн' in найдено) \
                and not PL.из_списка(r['site']):
            continue
        из.append({'inn': inn, 'name': r['name'], 'okved': r['okved'], 'site': r['site'],
                   'ulики': '+'.join(найдено) or 'улик нет',
                   'produkciya': _спискок(d.get('продукция')),
                   'citata': _спискок(d.get('цитата')),
                   'klienty': _спискок(d.get('клиенты'), 4)})
    if предел and len(из) > предел:
        random.seed(20260816)
        из = random.sample(из, предел)
    return из


def прогон(предел=400, потоков=10):
    import gen_provider as GP
    список = задачи(предел)
    if not список:
        return {'нечего судить': True}
    клиент = GP.make_client()

    def один(z):
        try:
            msg = GP.call(клиент, [{'role': 'user', 'content': PROMPT % z}],
                          model=MODEL, attempts=3)
            о = GP.parse_json(msg)
        except Exception as e:  # noqa: BLE001
            return dict(z, verdikt='сбой', prichina=str(e)[:120])
        return dict(z, verdikt=о.get('verdikt', ''), uverennost=о.get('uverennost', ''),
                    prichina=(о.get('prichina') or '')[:200])

    t0 = time.time()
    итог = {'судили': 0, 'свой': 0, 'расходится': 0, 'чужой': 0, 'сбой': 0, 'примеры': []}
    with ThreadPoolExecutor(max_workers=потоков) as ex, \
            open(ОТВЕТЫ, 'a', encoding='utf-8') as f:
        for r in ex.map(один, список):
            итог['судили'] += 1
            итог[r['verdikt']] = итог.get(r['verdikt'], 0) + 1
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
            if r['verdikt'] == 'чужой' and len(итог['примеры']) < 10:
                итог['примеры'].append({'инн': r['inn'], 'имя': r['name'][:45],
                                        'сайт': r['site'], 'улики': r['ulики'],
                                        'причина': r['prichina'][:110]})
    итог['сек'] = round(time.time() - t0)
    return итог


def статистика():
    итог = {'всего_судили': 0}
    if not os.path.exists(ОТВЕТЫ):
        return итог
    with open(ОТВЕТЫ, encoding='utf-8') as f:
        for s in f:
            try:
                d = json.loads(s)
            except Exception:  # noqa: BLE001
                continue
            итог['всего_судили'] += 1
            итог[d.get('verdikt', '?')] = итог.get(d.get('verdikt', '?'), 0) + 1
    return итог


def main():
    a = sys.argv[1:]
    if not a or a[0] == '--stat':
        print(json.dumps(статистика(), ensure_ascii=False, indent=1))
    elif a[0] == '--zamer':
        print(json.dumps(прогон(int(a[1]) if len(a) > 1 else 400),
                         ensure_ascii=False, indent=1))
    elif a[0] == '--vse':
        while True:
            r = прогон(300)
            print(json.dumps(r, ensure_ascii=False), flush=True)
            if r.get('нечего судить'):
                break
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
