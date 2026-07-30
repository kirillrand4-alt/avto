# -*- coding: utf-8 -*-
"""Найти сайт через выдачу тем целям, у кого его нет в базе.

Замечание владельца 30.07: «в выгрузке может быть не все сайты компаний».
Верно, и это ровно тот класс ошибки, который мы весь день ловим: **«нет в
файле» не равно «нет сайта»**. `sites_from_obzvon` берёт только то, что уже
записано в колонке выгрузки, — 56 сайтов на 281 компанию. Остальные 225 не
безсайтовые, а непроверенные.

Здесь сайт ищется в выдаче через `find_site_via_xmlriver`: один запрос с
карточкой организации, официальный сайт берётся из карточки (правая колонка)
и только потом из органики.

Рубеж привязки — двойной, потому что чужой сайт хуже отсутствия сайта:
  * `_is_own_site` отсекает агрегаторы, справочники и маркетплейсы;
  * страница качается, и на ней ищется ИНН компании. Совпал — пишем в `site`
    (подтверждено), не совпал — в `cand_site` (кандидат, обходчик его не
    берёт как факт). Молча в `site` не пишем никогда.

Запуск: python sayty_dlya_celey.py [--targets ФАЙЛ] [--lim N] [--dry]
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB       # noqa: E402
import enrich_contacts as EC  # noqa: E402

СУХОЙ = '--dry' in sys.argv
ЦЕЛИ = (sys.argv[sys.argv.index('--targets') + 1] if '--targets' in sys.argv
        else r'C:\seostat\drop\celi_bez_tehlpr.jsonl')
ЛИМ = int(sys.argv[sys.argv.index('--lim') + 1]) if '--lim' in sys.argv else 200
ЖУРНАЛ = r'C:\sender\server\sayty_dlya_celey.jsonl'


# Реквизиты почти никогда не лежат на ГЛАВНОЙ: их держат в контактах, в
# разделе «о компании» или на отдельной странице реквизитов. Проверка только
# по главной дала 2 подтверждения из 33 — то есть 31 живой сайт ушёл в
# кандидаты и остался невидим для обходчика. Это была моя ловушка, а не
# свойство сайтов.
_ПУТИ = ('', '/contacts/', '/contacts', '/kontakty/', '/kontakty',
         '/about/', '/o-kompanii/', '/rekvizity/', '/requisites/')


def _качать(урл):
    import urllib.request
    try:
        зпр = urllib.request.Request(урл, headers={'User-Agent': 'Mozilla/5.0'})
        return urllib.request.urlopen(зпр, timeout=20).read().decode('utf-8', 'replace')
    except Exception:  # noqa: BLE001
        return ''


def инн_на_странице(сайт, инн):
    """ИНН на главной ИЛИ на странице реквизитов. Ничего не нашли → False."""
    цифры = re.sub(r'\D', '', инн)
    осн = сайт.rstrip('/')
    for путь in _ПУТИ:
        html = _качать(осн + путь)
        if not html:
            continue
        if re.search(r'(?<!\d)' + цифры + r'(?!\d)', re.sub(r'[\s\-]', '', html)):
            return True, путь or '/'
    return False, ''


def _инн_на_главной_старое(сайт, инн):
    """Прежняя версия — только главная. Оставлена как памятка об ошибке."""
    try:
        html = EC.fetch(сайт) if hasattr(EC, 'fetch') else ''
    except Exception:  # noqa: BLE001
        html = ''
    if not html:
        try:
            import urllib.request
            зпр = urllib.request.Request(
                сайт, headers={'User-Agent': 'Mozilla/5.0'})
            html = urllib.request.urlopen(зпр, timeout=25).read().decode(
                'utf-8', 'replace')
        except Exception:  # noqa: BLE001
            return False, ''
    цифры = re.sub(r'\D', '', инн)
    есть = bool(re.search(r'(?<!\d)' + цифры + r'(?!\d)', re.sub(r'[\s\-]', '', html)))
    return есть, html[:0]


def main():
    if not os.path.exists(ЦЕЛИ):
        raise SystemExit(f'нет файла целей {ЦЕЛИ}')
    цели = []
    with open(ЦЕЛИ, encoding='utf-8') as ф:
        for строка in ф:
            try:
                цели.append(json.loads(строка))
            except Exception:  # noqa: BLE001
                continue
    db = EDB.EnrichDB()
    q = db.cx.execute
    есть_сайт = {r[0] for r in q(
        "SELECT inn FROM companies WHERE site IS NOT NULL AND site != ''").fetchall()}
    работа = [c for c in цели if c['inn'] not in есть_сайт][:ЛИМ]
    print(f'целей в файле: {len(цели)}, из них БЕЗ сайта в базе: {len(работа)}')
    sys.stdout.flush()
    if not работа:
        print('нечего искать')
        return

    подтв, кандидат, пусто, ошибок = 0, 0, 0, 0
    начало = time.time()
    for i, c in enumerate(работа, 1):
        if time.time() - начало > 1100:
            print(f'бюджет времени вышел на {i} из {len(работа)}')
            break
        имя = c.get('poln') or c.get('krat') or ''
        try:
            сайт, откуда, _карта = EC.find_site_via_xmlriver(
                {'name': имя, 'city': c.get('region') or ''})
        except Exception as e:  # noqa: BLE001
            ошибок += 1
            print(f'  {c["inn"]}: {str(e)[:70]}')
            continue
        if not сайт:
            пусто += 1
            if откуда.startswith('xmlriver-err') or откуда == 'no-xmlriver-key':
                ошибок += 1
                print(f'  {c["inn"]}: {откуда}')
            continue
        совпал, _ = инн_на_странице(сайт, c['inn'])
        запись = {'инн': c['inn'], 'имя': имя[:70], 'сайт': сайт,
                  'откуда': откуда, 'инн_на_странице': совпал}
        with open(ЖУРНАЛ, 'a', encoding='utf-8') as ж:
            ж.write(json.dumps(запись, ensure_ascii=False) + '\n')
            ж.flush()
            os.fsync(ж.fileno())
        if not СУХОЙ:
            if совпал:
                db.upsert_company(c['inn'], site=сайт)
            else:
                db.upsert_company(c['inn'], cand_site=сайт)
        подтв += 1 if совпал else 0
        кандидат += 0 if совпал else 1
        if i % 20 == 0:
            print(f'  … {i}/{len(работа)}: подтверждено {подтв}, '
                  f'кандидатов {кандидат}, пусто {пусто}')
            sys.stdout.flush()

    было = len(есть_сайт)
    стало = q("SELECT COUNT(*) FROM companies WHERE site IS NOT NULL "
              "AND site != ''").fetchone()[0]
    print()
    print('=== ИЗ БАЗЫ (не из счётчиков прогона) ===')
    print(f'  компаний с подтверждённым сайтом: было {было} → стало {стало} '
          f'(+{стало - было})')
    print(f'  подтверждено ИНН на странице: {подтв}, в кандидаты: {кандидат}, '
          f'выдача пуста: {пусто}, ошибок: {ошибок}')
    print(f'обработано {min(len(работа), ЛИМ)}, подтв {подтв}, канд {кандидат}')


if __name__ == '__main__':
    main()
