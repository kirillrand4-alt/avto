# -*- coding: utf-8 -*-
"""Сайт предприятия с карточки работодателя на hh — источник, который мы не брали.

У карточки работодателя на hh есть поле `site_url`, и заполняют его сами
компании. Это независимый от выдачи источник: там, где Яндекс отдаёт справочник
или молчит, hh может знать домен точно. Мы ходили на hh только за вакансиями
техслужбы и это поле не забирали.

Привязка — та же двухступенчатая, ослаблять её нельзя:
  1. работодатель ищется по ЯДРУ имени, и срабатывает рубеж тёзок из
     `hh_bez_tehlpr` (иначе «АО БМК» даёт 69 совпадений, первое из которых —
     транспортная фирма);
  2. найденный домен проверяется на ИНН нашей компании — главная плюс
     внутренние ссылки «реквизиты/контакты/о компании» (та же функция, что у
     доразбора кандидатов). Совпал ИНН — пишем в `site`. Не совпал — только в
     `cand_site`, молча сайтом не объявляем.

Durable: журнал `sayty_s_hh.jsonl` с flush+fsync на каждую цель, запись —
штатным `upsert_company`. Резюмируемо по журналу.

Запуск: python sayty_s_hh.py [--targets ФАЙЛ] [--lim N] [--budget СЕК] [--dry]
"""
import csv
import io
import json
import os
import sys
import time
import urllib.parse
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\server\ops')
import enrich_db as EDB           # noqa: E402
import hh_bez_tehlpr as HH        # noqa: E402
import kandidaty_sajtov as K      # noqa: E402

СУХОЙ = '--dry' in sys.argv


def арг(имя, поум):
    return sys.argv[sys.argv.index(имя) + 1] if имя in sys.argv else поум


ЦЕЛИ = арг('--targets', r'C:\seostat\drop\drop-storage\BEZ-TEHLPR-1486.csv')
ЛИМ = int(арг('--lim', '400'))
БЮДЖЕТ = float(арг('--budget', '1100'))
ЖУРНАЛ = r'C:\sender\server\sayty_s_hh.jsonl'


def main():
    tok = HH.токен()
    if not tok:
        print('НЕТ токена hh — без него api.hh.ru отдаёт 403, идти некуда')
        return

    csv.field_size_limit(10 ** 7)
    ряды = list(csv.DictReader(io.StringIO(
        open(ЦЕЛИ, encoding='utf-8-sig', errors='replace').read()),
        delimiter=';'))

    db = EDB.EnrichDB()
    q = db.cx.execute
    имена, есть_сайт = {}, set()
    for и, н, с in q("SELECT inn,COALESCE(name,''),COALESCE(site,'') "
                     'FROM companies'):
        имена[и] = н
        if с.strip():
            есть_сайт.add(и)
    пройдены = set()
    if os.path.exists(ЖУРНАЛ):
        for ln in open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
            try:
                пройдены.add(json.loads(ln).get('инн'))
            except Exception:  # noqa: BLE001
                continue

    работа = []
    for r in ряды:
        и = (r.get('inn') or '').strip()
        if not и or и in есть_сайт or и in пройдены:
            continue
        имя = (имена.get(и) or (r.get('predpriyatie') or '')).strip()
        if имя:
            работа.append((и, имя))
    работа = работа[:ЛИМ]
    print(f'целей в файле: {len(ряды)}; уже с сайтом: {len(есть_сайт)}; '
          f'пройдены ранее: {len(пройдены)}; в работу: {len(работа)}', flush=True)
    if not работа:
        print('работать не с чем')
        return

    было = q("SELECT COUNT(*) FROM companies WHERE COALESCE(site,'')<>''"
             ).fetchone()[0]
    итог = Counter()
    подтв = канд = 0
    начало = time.time()
    for i, (инн, имя) in enumerate(работа, 1):
        if time.time() - начало > БЮДЖЕТ:
            print(f'бюджет вышел на {i} из {len(работа)}', flush=True)
            break
        я = HH.ядро_имени(имя) or имя
        try:
            наш = HH.зпр('https://api.hh.ru/employers?text='
                         + urllib.parse.quote(я[:60]) + '&per_page=3', tok)
        except Exception as e:  # noqa: BLE001
            итог['employers ошибка'] += 1
            continue
        раб = (наш.get('items') or [])
        if HH.не_нашли(раб):
            итог['работодателя на hh нет'] += 1
            зап = {'инн': инн, 'имя': имя[:60], 'итог': 'работодателя нет'}
        else:
            отказ = HH.чужой_rabotodatel(я, раб[0].get('name', ''),
                                         наш.get('found', 0))
            if отказ:
                итог['отклонён как тёзка'] += 1
                зап = {'инн': инн, 'имя': имя[:60], 'итог': 'тёзка',
                       'почему': отказ[:80]}
            else:
                eid = раб[0]['id']
                try:
                    карт = HH.зпр(f'https://api.hh.ru/employers/{eid}', tok)
                except Exception:  # noqa: BLE001
                    карт = {}
                сайт = (карт.get('site_url') or '').strip()
                if not сайт:
                    итог['в карточке hh сайта нет'] += 1
                    зап = {'инн': инн, 'имя': имя[:60], 'eid': eid,
                           'итог': 'сайта в карточке нет'}
                else:
                    где = ''
                    try:
                        где = K.проверить(инн, сайт)
                    except Exception:  # noqa: BLE001
                        где = ''
                    if где:
                        подтв += 1
                        итог['ИНН на сайте совпал'] += 1
                        if not СУХОЙ:
                            db.upsert_company(инн, site=сайт)
                    else:
                        канд += 1
                        итог['сайт есть, ИНН не подтверждён'] += 1
                        if not СУХОЙ:
                            db.upsert_company(инн, cand_site=сайт)
                    зап = {'инн': инн, 'имя': имя[:60], 'eid': eid,
                           'сайт': сайт, 'где_инн': где,
                           'итог': 'подтверждён' if где else 'кандидат'}
        with open(ЖУРНАЛ, 'a', encoding='utf-8') as ж:
            ж.write(json.dumps(зап, ensure_ascii=False) + '\n')
            ж.flush()
            os.fsync(ж.fileno())
        if i % 40 == 0:
            print(f'  … {i}/{len(работа)}: подтв {подтв}, канд {канд}, '
                  f'{time.time() - начало:.0f}с', flush=True)

    стало = q("SELECT COUNT(*) FROM companies WHERE COALESCE(site,'')<>''"
              ).fetchone()[0]
    print()
    print('=== ИЗ БАЗЫ (не из счётчиков прогона) ===')
    print(f'  компаний с подтверждённым сайтом: было {было} → стало {стало} '
          f'(+{стало - было})')
    print('  что происходило:')
    for к, n in итог.most_common():
        print(f'    {n:>5}  {к}')
    print('ИТОГ ' + json.dumps({'подтверждено': подтв, 'кандидатов': канд,
                                'секунд': round(time.time() - начало)},
                               ensure_ascii=False))


if __name__ == '__main__':
    main()
