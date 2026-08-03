# -*- coding: utf-8 -*-
"""Разбор 43 кандидатов на возврат из файла 3-й сессии — решением держателя панели.

3-я сессия отобрала из 882 скрытий предприятий 43 с уликами «воздушная» и
честно предупредила: внутри есть Рутс и боковой канал (AERZEN GM, ROBUSCHI,
KAESER BB, FPZ SCL) — они НЕ центробежные, скрытие по типу там верное.
«Сама не разблокирую — решение за тем, кто держит панель». Панель держу я.

КРИТЕРИЙ ВОЗВРАТА — тот же словарь, что решил очередь «не установлено»:
  * марка в цитате опознана `razobrat` с nash_profil=True, ЛИБО
  * в цитате прямое слово центробежности (центробежн/турбовоздуходувк/
    турбокомпрессор воздуха) И нет опровержения роторности.
Роторные/вихревые бренды и слова (Рутс, боковой канал, roots) — НЕ возврат.

По умолчанию сухой прогон. Запуск: python vozvrat_43.py [--apply]
"""
import csv
import json
import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, r'C:\seostat')
from app.services import centro_marki as CMK  # noqa: E402

ПР = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
ДРОП = r'C:\seostat\drop\drop-storage'
ФАЙЛ = 'VAZHNOE-3s-SKRYTIYA-VOZDUSHNYE-K-VOZVRATU.csv'
ПРИМЕНИТЬ = '--apply' in sys.argv

_РОТОРНОЕ = re.compile(
    r'aerzen\s*gm|robuschi|kaeser\s*bb|fpz|\bscl\b|\brute?s\b|рутс|боков\w*\s+канал|'
    r'вихрев|роторн\w*\s+воздуходувк', re.I)
_ЦБ = re.compile(r'центробежн|турбовоздуходувк|турбокомпрессор|турбонагнетат', re.I)
_КАНДИДАТ = re.compile(
    r'\d{0,3}[A-ZА-Яa-zа-я]{1,6}\s?[-–]?\s?\d[\dA-ZА-Яa-zа-я,./\-]{0,26}')


def суждение(цитата):
    if _РОТОРНОЕ.search(цитата):
        return '', 'роторная/вихревая — скрытие верное'
    for сов in _КАНДИДАТ.finditer(цитата[:400]):
        к = сов.group(0).strip(' .,;')
        try:
            р = CMK.razobrat(к)
        except Exception:  # noqa: BLE001
            р = None
        if р and р.get('nash_profil'):
            return f'марка из словаря: {к}', ''
    if _ЦБ.search(цитата):
        return 'центробежность названа в тексте улики', ''
    return '', 'ни марки из словаря, ни слова центробежности'


def main():
    csv.field_size_limit(10 ** 7)
    путь = os.path.join(ДРОП, ФАЙЛ)
    if not os.path.exists(путь):
        raise SystemExit(f'нет {ФАЙЛ} на дропе')
    строки = []
    with open(путь, encoding='utf-8-sig', errors='replace', newline='') as ф:
        ч = csv.DictReader(ф, delimiter=';')
        for r in ч:
            строки.append(r)
    print(f'в файле строк: {len(строки)}; колонки: {list(строки[0])[:8]}')

    вернуть, оставить = [], []
    for r in строки:
        и = re.sub(r'\D', '', str(r.get('inn') or ''))[:12]
        цит = ' '.join(str(r.get(к) or '') for к in ('citata', 'prichina',
                                                     'reason', 'quote'))
        за, против = суждение(цит)
        (вернуть if за else оставить).append((и, за or против, цит[:100]))
    print(json.dumps({'ВЕРНУТЬ': len(вернуть), 'оставить_скрытыми': len(оставить),
                      'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой (--apply)'},
                     ensure_ascii=False))
    for и, п, ц in вернуть:
        print(f'  + {и} {п[:44]:44} {ц[:120]}')
    print('  --- остаются скрытыми:')
    for и, п, ц in оставить[:12]:
        print(f'  - {и} {п[:44]:44} {ц[:120]}')
    if not ПРИМЕНИТЬ or not вернуть:
        return
    пр = sqlite3.connect(ПР, timeout=20)
    пр.execute('PRAGMA busy_timeout=20000')
    сейчас = time.strftime('%Y-%m-%dT%H:%M:%S')
    было = пр.execute("SELECT COUNT(*) FROM hidden_item WHERE kind='company'").fetchone()[0]
    for и, п, _ц in вернуть:
        пр.execute("DELETE FROM hidden_item WHERE kind='company' AND inn=?", (и,))
    пр.commit()
    стало = пр.execute("SELECT COUNT(*) FROM hidden_item WHERE kind='company'").fetchone()[0]
    пр.close()
    print(json.dumps({'скрытий_было': было, 'стало': стало,
                      'снято': было - стало, 'ts': сейчас}, ensure_ascii=False))


if __name__ == '__main__':
    main()
