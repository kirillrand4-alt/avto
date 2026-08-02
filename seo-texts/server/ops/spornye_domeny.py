# -*- coding: utf-8 -*-
"""Домен, поделённый двумя ИНН: выяснить чей он, и вернуть цель в обход.

Обход подразделений пропускает такой домен ЦЕЛИКОМ и правильно делает: по
домену два юрлица не различить, а приписать человека не тому — хуже, чем не
приписать никому. Но пропускается при этом и настоящий владелец домена:
таких доменов 108, и за ними стоят живые цели.

Различить можно тем же способом, которым мы подтверждаем сам сайт: ИНН
печатают в реквизитах. Если на страницах домена нашёлся ИНН РОВНО ОДНОГО из
претендентов — домен его, у остальных это ошибка привязки (обычно управляющая
компания, дилер или однофамильное ООО, которому сайт приписала выдача).

Что делает оп: у проигравших `site` переносится в `cand_site`, а прежнее
значение пишется в журнал — восстановить можно построчно. Если ИНН не нашёлся
ни у кого или нашёлся у нескольких, домен остаётся спорным и не трогается:
молчаливое угадывание здесь недопустимо.

Durable: `spornye_domeny.jsonl` с flush+fsync. По умолчанию СУХОЙ ПРОГОН.

Запуск: python spornye_domeny.py [--targets ФАЙЛ] [--lim N] [--potokov N]
                                 [--budget СЕК] [--apply]
"""
import json
import os
import re
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\server\ops')
import enrich_db as EDB           # noqa: E402
import enrich_contacts as EC      # noqa: E402
import kandidaty_sajtov as K      # noqa: E402

ПРИМЕНИТЬ = '--apply' in sys.argv


def арг(имя, поум):
    return sys.argv[sys.argv.index(имя) + 1] if имя in sys.argv else поум


ЦЕЛЕВОЙ = арг('--targets', '')
ЛИМ = int(арг('--lim', '150'))
ПОТОКОВ = int(арг('--potokov', '6'))
БЮДЖЕТ = float(арг('--budget', '1000'))
ЖУРНАЛ = r'C:\sender\server\spornye_domeny.jsonl'
_ЗАМОК = threading.Lock()


def страницы_домена(сайт):
    """Главная плюс внутренние ссылки «реквизиты/контакты/о компании»."""
    осн = (сайт or '').rstrip('/')
    if not осн.startswith('http'):
        осн = 'http://' + осн
    дом = EC.site_domain(осн)
    главная = K._качать(осн)
    отдать = [(осн + '/', главная)]
    if not главная:
        return дом, отдать
    видели = set()
    import urllib.parse
    for адрес, текст in K._ССЫЛКА.findall(главная):
        подпись = K._ТЕГИ.sub(' ', текст)
        if not (K._ПОХОЖЕ.search(подпись) or K._ПОХОЖЕ.search(адрес)):
            continue
        полный = urllib.parse.urljoin(осн + '/', адрес.strip())
        if EC.site_domain(полный) != дом or полный in видели:
            continue
        видели.add(полный)
        if len(видели) > 12:
            break
    for у in видели:
        отдать.append((у, K._качать(у)))
    return дом, отдать


def main():
    db = EDB.EnrichDB()
    q = db.cx.execute
    по_дом = defaultdict(set)
    сайт_по_инн = {}
    for и, с in q("SELECT inn,site FROM companies WHERE COALESCE(site,'')<>''"):
        д = EC.site_domain(с)
        if д:
            по_дом[д].add(и)
            сайт_по_инн[и] = с
    спорные = {д: sorted(s) for д, s in по_дом.items() if len(s) > 1}

    хочу = None
    if ЦЕЛЕВОЙ:
        хочу = set()
        for ln in open(ЦЕЛЕВОЙ, encoding='utf-8-sig', errors='replace'):
            m = re.search(r'\b(\d{10}|\d{12})\b', ln)
            if m:
                хочу.add(m.group(1))
        спорные = {д: s for д, s in спорные.items()
                   if any(и in хочу for и in s)}

    # Пропускаем только то, что УЖЕ ПРИМЕНЕНО. Если считать пройденным всё,
    # что попало в журнал, то сухой прогон сам себе перекрывает боевой: он
    # честно записывает решения, а следующий запуск с --apply видит домены
    # «пройденными» и не делает ничего.
    пройдены = set()
    if os.path.exists(ЖУРНАЛ):
        for ln in open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if з.get('применено') or з.get('решение') == 'остаётся спорным':
                пройдены.add(з.get('домен'))
    работа = [(д, s) for д, s in sorted(спорные.items()) if д not in пройдены]
    работа = работа[:ЛИМ]
    print(f'спорных доменов: {len(спорные)}; пройдено ранее: {len(пройдены)}; '
          f'в работу: {len(работа)}; режим: '
          f'{"ПРИМЕНЕНИЕ" if ПРИМЕНИТЬ else "сухой"}', flush=True)
    if not работа:
        print('разбирать нечего')
        return

    начало = time.time()
    стоп = threading.Event()

    def одна(з):
        дом, претенденты = з
        if стоп.is_set():
            return None
        сайт = сайт_по_инн.get(претенденты[0], дом)
        try:
            _д, стр = страницы_домена(сайт)
        except Exception as e:  # noqa: BLE001
            return {'домен': дом, 'претенденты': претенденты,
                    'ошибка': str(e)[:60], 'решение': 'не решено'}
        нашлись = {}
        for и in претенденты:
            цифры = re.sub(r'\D', '', и)
            for у, h in стр:
                if K._есть_инн(h, цифры):
                    нашлись[и] = у
                    break
        if len(нашлись) == 1:
            победитель = next(iter(нашлись))
            return {'домен': дом, 'претенденты': претенденты,
                    'победитель': победитель, 'где': нашлись[победитель],
                    'проигравшие': [и for и in претенденты if и != победитель],
                    'страниц_смотрели': len(стр), 'решение': 'разрешён'}
        return {'домен': дом, 'претенденты': претенденты,
                'нашлись': list(нашлись), 'страниц_смотрели': len(стр),
                'решение': 'остаётся спорным'}

    разрешено = осталось = ошибок = 0
    снято = 0
    решения = []
    with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
        будущие = [пул.submit(одна, з) for з in работа]
        for ф in as_completed(будущие):
            if time.time() - начало > БЮДЖЕТ:
                стоп.set()
            зап = ф.result()
            if зап is None:
                continue
            if зап.get('ошибка'):
                ошибок += 1
            elif зап['решение'] == 'разрешён':
                разрешено += 1
                # прежние значения В ЖУРНАЛ до изменения — чтобы вернуть
                зап['снято_у'] = {и: сайт_по_инн.get(и, '')
                                  for и in зап['проигравшие']}
                if ПРИМЕНИТЬ:
                    with _ЗАМОК:
                        for и in зап['проигравшие']:
                            стар = сайт_по_инн.get(и, '')
                            db.cx.execute(
                                'UPDATE companies SET site=?, cand_site=?, '
                                'updated_at=? WHERE inn=?',
                                ('', стар, db.now, и))
                            снято += 1
                        db.cx.commit()
                зап['применено'] = bool(ПРИМЕНИТЬ)
            else:
                осталось += 1
            решения.append(зап)
            with _ЗАМОК:
                with open(ЖУРНАЛ, 'a', encoding='utf-8') as ж:
                    ж.write(json.dumps(зап, ensure_ascii=False) + '\n')
                    ж.flush()
                    os.fsync(ж.fileno())

    # числа — пересчётом по базе, не по счётчикам
    по_дом2 = defaultdict(set)
    for и, с in q("SELECT inn,site FROM companies WHERE COALESCE(site,'')<>''"):
        д = EC.site_domain(с)
        if д:
            по_дом2[д].add(и)
    спорных_стало = sum(1 for s in по_дом2.values() if len(s) > 1)
    print()
    print('=== ИЗ БАЗЫ (не из счётчиков прогона) ===')
    print(f'  спорных доменов всего в базе: было {len(по_дом) and sum(1 for s in по_дом.values() if len(s) > 1)} '
          f'→ стало {спорных_стало}')
    примеры = [з for з in решения if з.get('решение') == 'разрешён'][:6]
    for з in примеры:
        print(f"  {з['домен']}: победил {з['победитель']} "
              f"(ИНН найден на {з['где'][:60]}), снимаем у "
              f"{','.join(з['проигравшие'])}")
    print('ИТОГ ' + json.dumps(
        {'разобрано': len(работа), 'разрешено': разрешено,
         'остались_спорными': осталось, 'ошибок': ошибок,
         'снято_привязок': снято, 'секунд': round(time.time() - начало)},
        ensure_ascii=False))


if __name__ == '__main__':
    main()
