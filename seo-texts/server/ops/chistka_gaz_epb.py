# -*- coding: utf-8 -*-
"""Убрать из панельных фактов ГАЗОВЫЕ машины, протёкшие старым гейтом доливки ЭПБ.

ОТКУДА. Доливка реестра ЭПБ (`dolivka_epb_faktov.py`) до 03.08 пускала факт по
условию «слово центробежн есть в типе». Условие слишком широкое: центробежный
нагнетатель ГПА (Н-370, НЦ-16) и газовые К-400-51-2 проходили как «наша
машина». С 03.08 гейт спрашивает `nash_profil`, который учитывает среду, но уже
влитые газовые факты этим не убрать — их надо удалить точечно.

ПОЧЕМУ ПРЯМО В centrifugal.db, а не через enrich.db. Таблица `fact` — особый
случай: `build_centrifugal_db.py` её НЕ трогает (дропает только company/contact/
signal/person), факты копятся прямо в centrifugal.db опами доливки. Значит и
чистка здесь durable — пересборка её не откатит. Перед удалением делаем .bak,
как сама доливка.

Критерий газовости — тот же, что новый гейт: марка опознана справочником как
центробежная, но `nash_profil=False` (среда газ), ЛИБО газ назван в тексте
(ГПА, магистраль, трансгаз, нагнетатель газа).

По умолчанию СУХОЙ ПРОГОН. Запуск: python chistka_gaz_epb.py [--apply]
"""
import json
import os
import re
import shutil
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r'C:\seostat')
from app.services import centro_marki as CMK  # noqa: E402

БАЗА = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПРИМЕНИТЬ = '--apply' in sys.argv
_ГАЗ_ТЕКСТ = re.compile(
    r'\bгпа\b|газоперекачивающ|магистральн\w*\s+газопр|трансгаз|'
    r'нагнетател\w*\s+(?:природн\w*\s+)?газ|дожимн\w*\s+компресс|перекачк\w*\s+газ',
    re.I)


def газовый(модель, тип, цитата):
    """Тот же разбор, что в новом гейте доливки."""
    for кус in re.split(r'[|;/]|,(?!\d)', str(модель or '')):
        к = кус.strip()
        if not к:
            continue
        try:
            р = CMK.razobrat(к)
        except Exception:  # noqa: BLE001
            р = None
        if р and 'центробежн' in str(р.get('tip', '')).lower() \
                and not р.get('nash_profil'):
            return f'марка {к}: {р.get("sreda", "газ")[:24]}'
    if _ГАЗ_ТЕКСТ.search(f'{тип} {цитата}'):
        return 'газ назван в тексте'
    return ''


def main():
    cx = sqlite3.connect(f'file:{БАЗА}?mode=ro', uri=True, timeout=20)
    строки = list(cx.execute(
        "SELECT rowid, inn, COALESCE(model,''), COALESCE(equipment_type,''), "
        "COALESCE(quote,''), COALESCE(source,'') FROM fact "
        "WHERE source LIKE '%реестр ЭПБ%'"))
    cx.close()
    к_удалению = []
    причины = Counter()
    предпр = set()
    for rowid, инн, модель, тип, цит, ист in строки:
        п = газовый(модель, тип, цит)
        if п:
            к_удалению.append(rowid)
            причины[п.split(':')[0]] += 1
            предпр.add(str(инн))
    print(json.dumps({
        'фактов_ЭПБ_всего': len(строки),
        'К_УДАЛЕНИЮ_газовых': len(к_удалению),
        'предприятий_затронуто': len(предпр),
        'разбивка_причин': причины.most_common(),
        'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой (--apply)',
    }, ensure_ascii=False, indent=1))
    for rowid, инн, модель, тип, цит, ист in строки[:0]:
        pass
    примеры = [(инн, модель) for rowid, инн, модель, тип, цит, ист in строки
               if rowid in set(к_удалению)][:10]
    for инн, м in примеры:
        print(f'  - {инн} {м[:40]}')

    if not ПРИМЕНИТЬ or not к_удалению:
        if not ПРИМЕНИТЬ:
            print('\nсухой прогон. Повторить с --apply')
        return
    коп = БАЗА + '.bak-' + str(int(time.time()))
    shutil.copy2(БАЗА, коп)
    print(f'бэкап: {os.path.basename(коп)}')
    cx = sqlite3.connect(БАЗА, timeout=60)
    cx.execute('PRAGMA busy_timeout=60000')
    было = cx.execute("SELECT COUNT(*) FROM fact").fetchone()[0]
    cx.executemany('DELETE FROM fact WHERE rowid=?',
                   [(r,) for r in к_удалению])
    cx.commit()
    стало = cx.execute("SELECT COUNT(*) FROM fact").fetchone()[0]
    осталось_эпб_газ = 0
    for rowid, инн, модель, тип, цит, ист in cx.execute(
            "SELECT rowid, inn, COALESCE(model,''), COALESCE(equipment_type,''),"
            " COALESCE(quote,''), COALESCE(source,'') FROM fact "
            "WHERE source LIKE '%реестр ЭПБ%'"):
        if газовый(модель, тип, цит):
            осталось_эпб_газ += 1
    cx.close()
    print(json.dumps({'фактов_было': было, 'стало': стало,
                      'удалено': было - стало,
                      'газовых_ЭПБ_осталось': осталось_эпб_газ},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
