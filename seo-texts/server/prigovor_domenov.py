# -*- coding: utf-8 -*-
r"""Приговор модели по спорным привязкам мульти-ИНН доменов.

Вход — prigovor-ochered.jsonl из chistka_multi_inn.py: 3840 живых привязок,
где на страницах нет реквизитов компании. Здесь живут вперемешку филиалы
холдингов на сайте группы (привязка верна) и тёзки-прилипалы (автошкола
avtoschool-vektor.ru у четырнадцати «Векторов» — привязка ложь). Различит
только содержимое, поэтому судит модель — по правилам владельца: тяжёлая
работа через провайдерский API, фоном, с резюмом.

Вердикты:
  свой       сайт этой компании;
  группа     сайт её холдинга/сети — привязка допустима, но паспорт описывает
             группу (пометим, письмо решит карточка);
  чужой      сайт другой организации — привязку снять, паспорт в карантин;
  не_понять  содержимого мало; нет_страниц — кэша нет, судить нечем (не вердикт,
             пересудится, когда обход привезёт страницы).

Durable: enrich.db (таблица prigovor_domenov) + prigovor-domenov.jsonl (fsync).
Резюм по таблице: судимые пропускаются, «нет_страниц» пересуживается при
появлении кэша.

    python prigovor_domenov.py --sudit [потоков]   судить очередь
    python prigovor_domenov.py --svod              что насудили
    python prigovor_domenov.py --primenit          снять «чужих» (отдельный шаг)
"""
import gzip
import json
import os
import re
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender\server', r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
ОЧЕРЕДИ = (os.path.join(DIR, 'prigovor-ochered.jsonl'),
           r'C:\sender\_tmp\prigovor-ochered.jsonl',
           r'C:\sender\server\prigovor-ochered.jsonl')
ЖУРНАЛ = os.path.join(DIR, 'prigovor-domenov.jsonl')
МОДЕЛЬ = os.environ.get('PRIGOVOR_MODEL', 'claude-fable-5')
СХЕМА = """CREATE TABLE IF NOT EXISTS prigovor_domenov(
    inn TEXT, domen TEXT, verdikt TEXT, pochemu TEXT, ts TEXT,
    PRIMARY KEY(inn, domen))"""
ВЕРДИКТЫ = ('свой', 'группа', 'чужой', 'не_понять')

ПРОМПТ = (
    'Ты сверяешь, принадлежит ли сайт компании. Компания: «%(имя)s», '
    'ИНН %(инн)s, регион «%(регион)s», ОКВЭД «%(оквэд)s». Домен: %(домен)s. '
    'Важно: этот домен привязан сразу к %(юрлиц)d разным юрлицам, поэтому '
    'совпадение имени с доменом НИЧЕГО не доказывает — среди претендентов '
    'тёзки. Суди только по содержимому страниц: чем занимается сайт, какой '
    'регион, какие реквизиты и бренды видны.\n'
    'Ответ СТРОГО JSON без markdown: {"verdikt": "свой|группа|чужой|не_понять", '
    '"pochemu": "одна короткая фраза"}.\n'
    '  свой — сайт именно этой компании (род занятий и география сходятся);\n'
    '  группа — корпоративный сайт её холдинга/сети, компания в него входит;\n'
    '  чужой — сайт другой организации или другого бизнеса (например сайт '
    'автошколы, а компания — завод);\n'
    '  не_понять — содержимого мало.\n'
    'Текст страниц:\n%(текст)s')


def _текст(inn, предел=9000):
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
        т = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h)).strip()
        if т:
            куски.append(т[:3000])
        if sum(len(x) for x in куски) > предел:
            break
    return '\n---\n'.join(куски)[:предел]


def _очередь():
    for п in ОЧЕРЕДИ:
        if os.path.exists(п):
            with open(п, encoding='utf-8') as f:
                return [json.loads(l) for l in f if l.strip()]
    return []


def _бд():
    c = sqlite3.connect(BD, timeout=120)
    c.execute(СХЕМА)
    return c


def судить(потоков=10):
    import gen_provider as GP
    очередь = _очередь()
    c = _бд()
    судимые = {}
    for r in c.execute('select inn, domen, verdikt from prigovor_domenov'):
        судимые[(str(r[0]), r[1])] = r[2]
    дела = []
    for з in очередь:
        было = судимые.get((з['inn'], з['домен']))
        if было in ВЕРДИКТЫ:
            continue                    # осуждён по существу
        if было == 'нет_страниц' and not os.path.exists(
                os.path.join(KESH, '%s.json.gz' % з['inn'])):
            continue                    # кэш так и не приехал
        дела.append(з)
    итог = {'в_очереди': len(очередь), 'к_суду': len(дела)}
    if not дела:
        print(json.dumps(итог, ensure_ascii=False))
        return 0
    klient = GP.make_client()
    замок = threading.Lock()

    def одно(з):
        т = _текст(з['inn'])
        if not т or len(т) < 300:
            return {**з, 'verdikt': 'нет_страниц', 'pochemu': 'кэш пуст или мал'}
        промпт = ПРОМПТ % {'имя': з['name'], 'инн': з['inn'],
                           'регион': з.get('region') or 'неизвестен',
                           'оквэд': (з.get('okved') or 'неизвестен')[:80],
                           'домен': з['домен'],
                           'юрлиц': з.get('юрлиц_на_домене') or 2, 'текст': т}
        try:
            отв = GP.call(klient, [{'role': 'user', 'content': промпт}],
                          model=МОДЕЛЬ, attempts=3)
            m = re.search(r'\{.*\}', отв or '', re.S)
            d = json.loads(m.group(0)) if m else {}
            в = d.get('verdikt', '')
            if в not in ВЕРДИКТЫ:
                return {**з, 'verdikt': 'сбой', 'pochemu': 'кривой ответ: %r' % (отв or '')[:120]}
            return {**з, 'verdikt': в, 'pochemu': str(d.get('pochemu', ''))[:200]}
        except Exception as ex:  # noqa: BLE001
            return {**з, 'verdikt': 'сбой', 'pochemu': repr(ex)[:160]}

    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    сделано = 0
    with open(ЖУРНАЛ, 'a', encoding='utf-8') as ж, \
            ThreadPoolExecutor(max_workers=потоков) as пул:
        будущие = [пул.submit(одно, з) for з in дела]
        for б in as_completed(будущие):
            r = б.result()
            with замок:
                if r['verdikt'] != 'сбой':      # сбой не пишем — пересудится
                    c.execute('INSERT OR REPLACE INTO prigovor_domenov'
                              '(inn, domen, verdikt, pochemu, ts) VALUES(?,?,?,?,?)',
                              (r['inn'], r['домен'], r['verdikt'], r['pochemu'], ts))
                    c.commit()
                ж.write(json.dumps(r, ensure_ascii=False) + '\n')
                ж.flush()
                os.fsync(ж.fileno())
                сделано += 1
                итог[r['verdikt']] = итог.get(r['verdikt'], 0) + 1
                if сделано % 50 == 0:
                    print('[%s] %d/%d %s' % (time.strftime('%H:%M:%S'), сделано,
                                             len(дела), json.dumps(итог, ensure_ascii=False)),
                          flush=True)
    c.close()
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0


def свод():
    c = _бд()
    из = {'по_вердиктам': dict(c.execute(
        'select verdikt, count(*) from prigovor_domenov group by 1').fetchall())}
    из['примеры_чужих'] = [dict(zip(('inn', 'domen', 'pochemu'), r)) for r in
                           c.execute("select inn, domen, pochemu from "
                                     "prigovor_domenov where verdikt='чужой' limit 8")]
    c.close()
    print(json.dumps(из, ensure_ascii=False, indent=1))
    return 0


def применить():
    c = _бд()
    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    чужие = list(c.execute("select inn, domen from prigovor_domenov "
                           "where verdikt='чужой'"))
    снято = карантин = 0
    for inn, домен in чужие:
        n = c.execute("UPDATE companies SET site=NULL, updated_at=? WHERE inn=? "
                      "AND coalesce(site,'') LIKE ?",
                      (ts, inn, '%' + домен + '%')).rowcount
        снято += n
        if n:
            карантин += c.execute(
                "UPDATE site_facts SET otkloneno_json=facts_json, facts_json='', "
                "privyazka=?, note=? WHERE inn=? AND coalesce(facts_json,'')<>''",
                ('приговор: чужой ' + домен,
                 'модель по содержимому: сайт другой организации', inn)).rowcount
    # группам паспорт не снимаем, но помечаем: описывает холдинг
    группы = c.execute("UPDATE site_facts SET privyazka='группа' WHERE inn IN "
                       "(select inn from prigovor_domenov where verdikt='группа') "
                       "AND coalesce(facts_json,'')<>''").rowcount
    c.commit()
    c.close()
    из = {'чужих_вердиктов': len(чужие), 'снято_привязок': снято,
          'паспортов_в_карантин': карантин, 'помечено_группой': группы}
    print(json.dumps(из, ensure_ascii=False, indent=1))
    return 0


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    if a and a[0] == '--sudit':
        n = int(a[1]) if len(a) > 1 and a[1].isdigit() else 10
        return судить(n)
    if a and a[0] == '--primenit':
        return применить()
    return свод()


if __name__ == '__main__':
    sys.exit(main())
