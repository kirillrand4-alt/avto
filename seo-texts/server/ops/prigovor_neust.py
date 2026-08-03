# -*- coding: utf-8 -*-
"""Приговоры очереди «не установлено» по правилу владельца: словарь решает.

ПРАВИЛО ВЛАДЕЛЬЦА (03.08, дословно): «доузнавай, одна сессия делает словарь,
по которому будут модели воздушные, если нет совпадений - то выкидываем».
Доузнавание сделано: реестр ЭПБ долит вместе с перепрошенными провайдером
строками (+2321 факт на 129 предприятий), справочник семейств расширен. Теперь
сам приговор — и он МЕХАНИЧЕСКИЙ, без единого вызова модели: словарь либо
опознал воздушную центробежную машину у предприятия, либо нет.

ЧТО СЧИТАЕТСЯ СОВПАДЕНИЕМ. Марка из фактов, которую `centro_marki.razobrat`
опознал с `nash_profil=True` — то есть центробежная И не газовая. Слово
«центробежный» в тексте без марки совпадением НЕ считается: правило владельца
про модели, а не про слова, и ровно на словах без марок эти предприятия уже
получили «не установлено».

ДВЕ СТРАХОВКИ, обе в пользу владельца:
  * «есть» ставится только если совпавшая марка стоит в НЕотклонённом факте;
  * скрытие пишет причину со словами «правило владельца», чтобы отличаться от
    приговоров суда моделей и сниматься отдельно, если правило поменяется.

Пишем в ОБА хранилища: sud_centro (enrich.db, серверное) и панель
(sud_verdikt + hidden_item). По умолчанию СУХОЙ ПРОГОН.

Запуск: python prigovor_neust.py [--apply]
"""
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\seostat')
import enrich_db as EDB  # noqa: E402
from app.services import centro_marki as CMK  # noqa: E402

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПР = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
ПРИМЕНИТЬ = '--apply' in sys.argv
_РЕЗ = re.compile(r'[|;/\n]|,(?!\d)')


def совпавшие_марки(модели):
    из = []
    for м in модели:
        for кусок in _РЕЗ.split(str(м or '')):
            к = кусок.strip()
            if len(к) < 3:
                continue
            try:
                р = CMK.razobrat(к)
            except Exception:  # noqa: BLE001
                р = None
            if р and р.get('nash_profil'):
                из.append(к)
    return из


def main():
    db = EDB.EnrichDB()
    неуст = {r[0] for r in db.cx.execute(
        "SELECT inn FROM sud_centro WHERE verdikt='не установлено'")}

    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    кол = [c[1] for c in цб.execute('PRAGMA table_info("company")')]
    имя_к = next((k for k in ('predpriyatie', 'name', 'name_full')
                  if k in кол), 'inn')
    имена = {str(r[0]): (r[1] or '') for r in цб.execute(
        f'SELECT inn, "{имя_к}" FROM company')}
    кол_ф = [c[1] for c in цб.execute('PRAGMA table_info("fact")')]
    отк = ('rejection_reason' if 'rejection_reason' in кол_ф
           else 'rejected' if 'rejected' in кол_ф else None)
    модели = {}
    зпр = "SELECT inn, COALESCE(model,'') FROM fact WHERE COALESCE(model,'')<>''"
    if отк:
        зпр += f" AND COALESCE(\"{отк}\",'') IN ('', '0')"
    for и, м in цб.execute(зпр):
        модели.setdefault(str(и), []).append(м)
    цб.close()

    пр = sqlite3.connect(ПР, timeout=20)
    пр.execute('PRAGMA busy_timeout=20000')
    скрыты = {str(r[0]) for r in пр.execute(
        "SELECT inn FROM hidden_item WHERE kind='company'")}

    видимые = sorted(и for и in неуст if и in имена and и not in скрыты)
    в_есть, в_скрыть = [], []
    for и in видимые:
        марки = совпавшие_марки(модели.get(и, []))
        if марки:
            топ = sorted(Counter(марки).items(), key=lambda x: -x[1])
            почему = ('модель из словаря воздушных центробежных: '
                      + ', '.join(м for м, _ in топ[:4])
                      + ' (правило владельца 03.08)')
            в_есть.append((и, почему[:380]))
        else:
            почему = ('марки в фактах не совпали со словарём воздушных '
                      'центробежных — выкидываем (правило владельца 03.08)')
            в_скрыть.append((и, почему))

    print(json.dumps({
        'не_установлено_всего': len(неуст),
        'из_них_видимых': len(видимые),
        'СТАНУТ_ЕСТЬ': len(в_есть),
        'БУДУТ_СКРЫТЫ': len(в_скрыть),
        'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой (--apply)',
    }, ensure_ascii=False, indent=1))
    print('\nстанут «есть» (первые 15):')
    for и, п in в_есть[:15]:
        print(f'  {и} {имена.get(и, "")[:44]:44} {п[:70]}')
    print('\nбудут скрыты (первые 10):')
    for и, _п in в_скрыть[:10]:
        print(f'  {и} {имена.get(и, "")[:60]}')

    if not ПРИМЕНИТЬ:
        пр.close()
        print('\nсухой прогон. Повторить с --apply')
        return

    сейчас = time.strftime('%Y-%m-%dT%H:%M:%S')
    # серверное хранилище — источник истины
    db.cx.executemany(
        'UPDATE sud_centro SET verdikt=?, uverennost=?, pochemu=?, ts=? '
        'WHERE inn=?',
        [('есть', 85, п, сейчас, и) for и, п in в_есть]
        + [('нет', 85, п, сейчас, и) for и, п in в_скрыть])
    db.cx.commit()
    # зеркало в панель
    пр.execute('CREATE TABLE IF NOT EXISTS sud_verdikt('
               'inn TEXT PRIMARY KEY, verdikt TEXT, uverennost INTEGER, '
               'pochemu TEXT, ts TEXT)')
    пр.executemany(
        'INSERT OR REPLACE INTO sud_verdikt(inn, verdikt, uverennost, pochemu, ts)'
        ' VALUES(?,?,?,?,?)',
        [(и, 'есть', 85, п[:400], сейчас) for и, п in в_есть]
        + [(и, 'нет', 85, п[:400], сейчас) for и, п in в_скрыть])
    пр.executemany(
        'INSERT OR REPLACE INTO hidden_item'
        '(inn, kind, value, reason, username, created_at) VALUES(?,?,?,?,?,?)',
        [(и, 'company', и, п[:200], 'admin', сейчас) for и, п in в_скрыть])
    пр.commit()
    видно = пр.execute(
        "SELECT COUNT(*) FROM company WHERE inn NOT IN "
        "(SELECT inn FROM hidden_item WHERE kind='company')").fetchone()[0] \
        if 'company' in [r[0] for r in пр.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")] else -1
    пр.close()
    print(json.dumps({'обновлено_есть': len(в_есть),
                      'скрыто': len(в_скрыть),
                      'видимых_компаний_в_панели': видно},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
