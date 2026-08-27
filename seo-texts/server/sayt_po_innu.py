# -*- coding: utf-8 -*-
r"""Пересмотреть привязку сайтов, сделанную по совпадению ИМЕНИ.

Владелец 27.08: «а ИНН есть у этих сайтов?» Прогон по всем 20 532 карточкам с
`site_source='xmlriver+имя-на-сайте'` (замер лежит в `inn-na-saytah.jsonl`):

  ПОДТВЕРЖДЕНО  258  на страницах напечатан НАШ ИНН — привязка доказана;
  ОПРОВЕРГНУТО 3196  ИНН есть, но чужой — кандидат в карантин;
  МОЛЧИТ      14321  реквизитов на сайте нет вовсе, судить не по чему;
  кэша нет     2757.

Из «опровергнутых» 180 держатся только на ИНН, встреченном у десятков разных
компаний, — это подвал конструктора сайтов, банка или партнёрской сети
(7707083893 — Сбербанк, встретился 17 раз). Такой ИНН уликой быть не может, и
эти карточки не трогаем. Твёрдых опровержений 3016.

Скрипт делает ТОЛЬКО безопасную половину: поднимает 258 подтверждённых из
«привязано по имени» в «инн-на-странице». Понижение опровергнутых — отдельное
решение владельца, потому что чужой ИНН на странице ещё не доказывает, что сайт
не наш: бывает холдинг, где операционное юрлицо другое.

    python sayt_po_innu.py            показать расклад
    python sayt_po_innu.py --povysit  поднять подтверждённые
"""
import json
import os
import sqlite3
import sys
import time

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
ЗАМЕР = r'C:\sender\_tmp\inn-na-saytah.jsonl'


def _zamer():
    ряды = []
    if not os.path.exists(ЗАМЕР):
        return ряды
    with open(ЗАМЕР, encoding='utf-8', errors='replace') as f:
        for s in f:
            try:
                ряды.append(json.loads(s))
            except Exception:  # noqa: BLE001
                pass
    return ряды


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ряды = _zamer()
    d = {'замерено': len(ряды)}
    по_классам = {}
    for r in ряды:
        по_классам[r['класс']] = по_классам.get(r['класс'], 0) + 1
    d['классы'] = по_классам
    подтв = [r['инн'] for r in ряды if r['класс'] == 'ПОДТВЕРЖДЕНО']
    d['подтверждённых'] = len(подтв)
    if '--povysit' not in sys.argv or not подтв:
        print(json.dumps(d, ensure_ascii=False, indent=1))
        return 0

    теперь = time.strftime('%Y-%m-%dT%H:%M:%S')
    c = sqlite3.connect(BD, timeout=20)
    c.execute('PRAGMA busy_timeout=15000')
    поднято = 0
    # Мелкими пачками: enrich.db непрерывно пишет цикл паспортов, длинная
    # транзакция туда не пролезает (проверено трижды за сутки).
    for i in range(0, len(подтв), 20):
        кусок = подтв[i:i + 20]
        for _ in range(60):
            try:
                c.execute('BEGIN IMMEDIATE')
                for инн in кусок:
                    c.execute("UPDATE companies SET site_source=? WHERE inn=? "
                              "AND site_source='xmlriver+имя-на-сайте'",
                              ('инн-на-странице', инн))
                    c.execute('INSERT INTO stage_log(inn, stage, detail, ts) '
                              'VALUES(?,?,?,?) ON CONFLICT(inn, stage) DO UPDATE '
                              'SET detail=excluded.detail, ts=excluded.ts',
                              (инн, 'sayt_dokazan',
                               'ИНН компании найден на её страницах', теперь))
                    поднято += 1
                c.commit()
                break
            except sqlite3.OperationalError:
                try:
                    c.rollback()
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(2)
    d['поднято'] = поднято
    d['теперь_инн_на_странице'] = c.execute(
        "select count(*) from companies where site_source='инн-на-странице'"
    ).fetchone()[0]
    c.close()
    print(json.dumps(d, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
