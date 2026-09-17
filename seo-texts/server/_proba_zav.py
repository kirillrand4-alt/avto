# -*- coding: utf-8 -*-
r"""Убрать события, которые уже завершились, и всё, что датировано 2024 и раньше.

Владелец 17.09: «то что уже на завершающей стадии, а особенно 2024 года нам точно
не нужно». Логика простая и проверяемая, без модели:

  * СТАРОЕ ПО ГОДУ — в тексте события есть годы, и самый поздний из них 2024 или
    раньше. Пример из базы: «Модернизация центра судоремонта «Звездочка»,
    завершение запланировано на 2024 год».
  * ЗАВЕРШЕНО — прямые слова о том, что объект уже пущен: завершено, введён в
    эксплуатацию, запущен, открыт, сдан. С оговоркой: «запущено строительство» и
    «запущен проект» — это НАЧАЛО стройки, их не трогаем.

Всё удаляемое сперва уходит в бэкап рядом с базой и на дроп.
Запуск: python chistka_zavershyonnyh.py [--proba]
"""
import io
import json
import os
import re
import sqlite3
import sys
import time

DIR = r'C:\sender\server'
БАЗА = r'C:\sender\enrich.db'

ГОД = re.compile(r'\b(20[1-3]\d)\b')
ЗАВЕРШЕНО = re.compile(
    r'заверш\w*|введ[её]н\w*|ввод\w*\s+в\s+эксплуатац|сдан\w*\s+в\s+эксплуатац|'
    r'запущен\w*|запустил\w*|открыл\w*|открыт\w+\s+(?:цех|завод|линия|производство)|'
    r'начал\w*\s+рабо|приступил\w*\s+к\s+выпуску|вышел\s+на\s+проектную', re.I)
НАЧАЛО = re.compile(
    r'запущен\w*\s+(?:строительств|проект|процесс)|'
    r'запуск\w*\s+строительств|начал\w*\s+строительств|'
    r'приступил\w*\s+к\s+строительств', re.I)


def разбор(what, стадия_текст):
    т = (what or '')
    годы = [int(g) for g in ГОД.findall(т)]
    старый_год = bool(годы) and max(годы) <= 2024
    завершено = bool(ЗАВЕРШЕНО.search(т)) and not НАЧАЛО.search(т)
    return старый_год, завершено


def main():
    проба = True
    c = sqlite3.connect(БАЗА, timeout=120)
    c.execute('pragma busy_timeout=120000')
    строки = c.execute(
        "select rowid, inn, source, event_type, what, coalesce(sum,''), hotness, "
        "coalesce(source_url,''), updated_at from signals").fetchall()
    было = len(строки)

    к_удалению, причины = [], {'старый год': 0, 'завершено': 0, 'и то и другое': 0}
    примеры = []
    for rid, inn, src, et, what, sm, hot, url, upd in строки:
        стар, зав = разбор(what, et)
        if not (стар or зав):
            continue
        причины['и то и другое' if стар and зав else
                'старый год' if стар else 'завершено'] += 1
        к_удалению.append(rid)
        if len(примеры) < 8:
            примеры.append({'причина': 'год' if стар else 'завершено',
                            'тип': et, 'что': (what or '')[:110]})

    итог = {'было': было, 'под_чистку': len(к_удалению), 'причины': причины,
            'останется': было - len(к_удалению), 'примеры': примеры}
    if проба or not к_удалению:
        c.close()
        итог['режим'] = 'проба'
        print('===ИТОГ===')
        print(json.dumps(итог, ensure_ascii=False, indent=1)[:3500])
        return 0

    бэк = os.path.join(DIR, 'udalyonnye-zavershyonnye-%s.jsonl' % time.strftime('%d%m-%H%M'))
    with io.open(бэк, 'w', encoding='utf-8') as f:
        for rid in к_удалению:
            р = c.execute(
                "select inn, source, event_type, what, coalesce(sum,''), hotness, "
                'coalesce(source_url,\'\'), updated_at from signals where rowid=?',
                (rid,)).fetchone()
            if р:
                f.write(json.dumps({'inn': р[0], 'источник': р[1], 'тип': р[2], 'что': р[3],
                                    'сумма': р[4], 'важность': р[5], 'ссылка': р[6],
                                    'узнали': р[7]}, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    try:
        import shutil
        shutil.copyfile(бэк, os.path.join(r'C:\seostat\drop\drop-storage',
                                          os.path.basename(бэк)))
    except Exception:  # noqa: BLE001
        pass
    n = 0
    for i in range(0, len(к_удалению), 400):
        куск = к_удалению[i:i + 400]
        n += c.execute('delete from signals where rowid in (%s)'
                       % ','.join('?' * len(куск)), куск).rowcount
    c.commit()
    стало = c.execute('select count(*) from signals').fetchone()[0]
    c.close()
    итог.update({'удалено': n, 'стало': стало, 'бэкап': os.path.basename(бэк)})
    print('===ИТОГ===')
    print(json.dumps(итог, ensure_ascii=False, indent=1)[:3500])
    return 0


if __name__ == '__main__':
    sys.exit(main())
