# -*- coding: utf-8 -*-
r"""База КЦ, шаг 2: итоговый список компаний.

  * из нашей базы (kc-pishch-otbor.json) — выручка >= 3 млрд;
  * из ФНС (kc-okved-fns.jsonl: доход 2025 >= 3 млрд, нет в наших базах) — основной ОКВЭД в сегментах;
  * без ликвидированных и без запретов панели (сделка, конкурент, не профиль, не покупатель);
  * для компаний из нашей базы — страницы-источники их контактов (свой домен и площадки закупок),
    чтобы обход сайта и проверка закупок их тоже открыли.
Выход (fsync): C:\sender\server\kc-spisok.json -> копия на дроп.
"""
import io
import json
import os
import re
import shutil
import sqlite3
import sys

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
os.chdir(DIR)
from kc_pishch_otbor import СЕГМЕНТЫ, ПОРОГ  # noqa: E402
from meyer_baza import коды, попадает_осн, имя_чисто  # noqa: E402
import meyer_nalichie as MN  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'
ВЫХОД = os.path.join(DIR, 'kc-spisok.json')
ЗАКУПКИ = re.compile(r'zakupki\.gov|tender\.pro|roseltorg|b2b-center|etpgpb|fabrikant|zakupki360|rts-tender|'
                     r'sberbank-ast|tektorg|lot-online|zakazrf|otc\.ru|onlinecontract|bicotender|etp-ets', re.I)


def сегмент(осн, все):
    сегм = [с for с, п in СЕГМЕНТЫ if попадает_осн(осн, все, п)]
    if 'сыры' in сегм and 'переработка молока' in сегм:
        сегм.remove('переработка молока')
    return сегм[0] if сегм else ''


def main():
    база = json.load(io.open(os.path.join(DIR, 'kc-pishch-otbor.json'), encoding='utf-8'))
    итог, снято = {}, {}
    for i, к in база.items():
        if к['выручка'] >= ПОРОГ:
            итог[i] = {'inn': i, 'имя': к['имя'], 'регион': к['регион'], 'сайт': (re.split(r'[\s,;|]+', к['сайт'].strip()) or [''])[0],
                       'осн': к['осн'], 'все': к['все'], 'сегм': к['сегм'], 'выручка': к['выручка'],
                       'выручка_откуда': к['выручка_откуда'], 'откуда': ', '.join(к['откуда']), 'огрн': ''}
    фнс = {}
    for s in io.open(os.path.join(DIR, 'kc-okved-fns.jsonl'), encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('итог') == 'ok' and з.get('оквэд'):
            фнс[з['inn']] = з
    for i, з in фнс.items():
        осн = (коды(з['оквэд'])[:1] or [''])[0]
        все = коды(з['оквэд'], ' '.join(з.get('оквэд_все') or []))
        с = сегмент(осн, все)
        if not с:
            continue
        if re.search(r'LIQUIDAT|BANKRUPT|ликвид', з.get('статус') or '', re.I):
            снято[i] = 'ликвидирована/банкрот (%s)' % з.get('статус')
            continue
        имя = з.get('название') or ''
        if з['источник'] == 'checko':  # заголовок карточки: «ООО "Х", Город — ИНН …»
            имя = re.split(r',\s|\s[—-]\s', имя)[0]
        итог[i] = {'inn': i, 'имя': имя_чисто(имя), 'регион': з.get('регион') or '', 'сайт': з.get('сайт') or '',
                   'осн': осн, 'все': все, 'сегм': с, 'выручка': з['доход'], 'выручка_откуда': 'ФНС (доход 2025)',
                   'откуда': 'ФНС: доход 2025 >= 3 млрд (%s)' % з['источник'], 'огрн': з.get('огрн') or ''}
    # запреты панели
    c = sqlite3.connect(r'file:C:\sender\sender.db?mode=ro', uri=True, timeout=60)
    т = [r[0] for r in c.execute("select name from sqlite_master where type='table' and name like '%suppress%'")][0]
    кол = [r[1] for r in c.execute('pragma table_info(%s)' % т)]
    for r in c.execute("select * from %s where scope='inn'" % т):
        x = dict(zip(кол, r))
        i = str(x['value'])
        if i in итог:
            rs, src = x.get('reason') or '', x.get('source') or ''
            снято[i] = ('идёт сделка (панель)' if rs == 'deal_in_progress' or 'сделка' in src.lower() else
                        'конкурент (панель)' if 'competitor' in rs or 'конкурент' in rs else '%s (панель)' % rs)
    c.close()
    снятые = {i: dict(итог.pop(i), причина=п) for i, п in снято.items() if i in итог}
    # страницы-источники контактов из нашей базы
    c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=120)
    c.execute('create temp table t(inn text primary key)')
    c.executemany('insert into t values (?)', [(i,) for i in итог])
    for i, url in c.execute("select inn, source_url from people where inn in (select inn from t) and coalesce(source_url,'')<>'' "
                            "union select inn, source_url from phone_contacts where inn in (select inn from t) and coalesce(source_url,'')<>''"):
        к = итог[str(i)]
        if ЗАКУПКИ.search(url):
            к.setdefault('закупки_базы', []).append(url)
        elif к['сайт'] and MN.домен(url) == MN.домен(к['сайт']):
            к.setdefault('страницы_базы', []).append(url)
    c.close()
    with io.open(ВЫХОД, 'w', encoding='utf-8') as f:
        json.dump({'компании': итог, 'снято': снятые}, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    shutil.copyfile(ВЫХОД, os.path.join(ДРОП, 'kc-spisok.json'))
    сч = {}
    for к in итог.values():
        сч[к['сегм']] = сч.get(к['сегм'], 0) + 1
    пр = {}
    for к in снятые.values():
        пр[к['причина']] = пр.get(к['причина'], 0) + 1
    print('===ИТОГ===')
    print(json.dumps({'компаний': len(итог), 'по_сегментам': сч, 'из_нашей_базы': sum(1 for к in итог.values() if not к['откуда'].startswith('ФНС')),
                      'новых_из_ФНС': sum(1 for к in итог.values() if к['откуда'].startswith('ФНС')),
                      'с_сайтом': sum(1 for к in итог.values() if к['сайт']), 'снято': пр,
                      'фнс_оквэд_получен': len(фнс)}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
