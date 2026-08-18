# -*- coding: utf-8 -*-
r"""Починка адресов, которые панель отвергает как невалидные.

Найдено 18.08 при разборе догруза: из партии 935 импорт отбросил 6 адресов, и
причина не в панели — сайты прячут почту от сборщиков, а мы забираем как есть:

  ba%6d_%74%70@tiz.ru      процентное кодирование: %6d%74%70 = m t p -> bam_tp@
  sаturn-oren@yandex.ru    кириллическая «а» внутри латинского слова (омоглиф)
  rys yatov.viktor@...     пробел внутри адреса
  ооо-sg-ooo@mail.ru       кириллические «ооо» в латинском адресе

Правила чинят ТОЛЬКО то, что после починки становится годным ascii-адресом;
если результат не проходит проверку — оставляем как было, ничего не выдумываем.
Настоящие кириллические адреса (почта@сайт.рф) не трогаем: их признак — вся
метка на кириллице, а не смесь.

    python pochinka_adresov.py            посчитать и показать примеры
    python pochinka_adresov.py --primenit починить в enrich.db
"""
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
ЖУРНАЛ = r'C:\sender\server\pochinka-adresov.jsonl'
ГОДЕН = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._+-]*@[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}$')
# кириллические буквы, неотличимые от латинских на глаз
ОМОГЛИФЫ = {'а': 'a', 'в': 'b', 'е': 'e', 'к': 'k', 'м': 'm', 'н': 'h', 'о': 'o',
            'р': 'p', 'с': 'c', 'т': 't', 'у': 'y', 'х': 'x', 'і': 'i', 'ѕ': 's',
            'А': 'A', 'В': 'B', 'Е': 'E', 'К': 'K', 'М': 'M', 'Н': 'H', 'О': 'O',
            'Р': 'P', 'С': 'C', 'Т': 'T', 'У': 'Y', 'Х': 'X'}
КИРИЛЛИЦА = re.compile(r'[а-яёА-ЯЁ]')
ЛАТИНИЦА = re.compile(r'[a-zA-Z]')


def починить(адрес):
    """(новый_адрес, чем_чинили) или (None, причина) — если не вышло."""
    s = str(адрес or '')
    чем = []
    if not s or ГОДЕН.match(s):
        return None, 'уже годен'
    if '%' in s:
        try:
            r = urllib.parse.unquote(s)
            if r != s:
                s, _ = r, чем.append('раскодировали %XX')
        except Exception:  # noqa: BLE001
            pass
    if re.search(r'\s', s):
        s = re.sub(r'\s+', '', s)
        чем.append('убрали пробелы')
    # омоглифы правим ТОЛЬКО в смешанных метках: чистая кириллица — это IDN
    if КИРИЛЛИЦА.search(s) and ЛАТИНИЦА.search(s):
        n = ''.join(ОМОГЛИФЫ.get(ch, ch) for ch in s)
        if n != s:
            s, _ = n, чем.append('кириллические омоглифы -> латиница')
    s = s.strip(' .,;:<>()[]"\'')
    # ведущий мусор локальной части: «-mailinfo@», «+lev1909@» — остаток
    # маркера списка на странице; адрес обязан начинаться с буквы или цифры
    н = re.sub(r'^[^a-zA-Z0-9а-яёА-ЯЁ]+', '', s)
    if н != s:
        s, _ = н, чем.append('срезали мусор в начале')
    if ГОДЕН.match(s) and чем:
        return s.lower(), ', '.join(чем)
    return None, 'починка не дала годного адреса'


def разбор(применять=False):
    c = sqlite3.connect(BD, timeout=90)
    c.row_factory = sqlite3.Row
    строки = list(c.execute("select inn, email from emails where coalesce(email,'')<>''"))
    итог = {'адресов_всего': len(строки), 'битых': 0, 'починили': 0,
            'не_поддались': 0, 'по_приёмам': {}, 'столкновений': 0}
    примеры, правки = [], []
    занято = {r['email'].lower() for r in строки}
    for r in строки:
        стар = r['email']
        if ГОДЕН.match(стар or ''):
            continue
        итог['битых'] += 1
        нов, чем = починить(стар)
        if not нов:
            итог['не_поддались'] += 1
            if len([1 for p in примеры if p['итог'] == 'не вышло']) < 4:
                примеры.append({'инн': str(r['inn']), 'было': стар[:60],
                                'итог': 'не вышло'})
            continue
        # адрес уже есть у этой же компании — чинить нечего, битый дубль удалим
        if нов in занято and нов != стар.lower():
            итог['столкновений'] += 1
        итог['починили'] += 1
        итог['по_приёмам'][чем] = итог['по_приёмам'].get(чем, 0) + 1
        правки.append((str(r['inn']), стар, нов, чем))
        if len([1 for p in примеры if p['итог'] != 'не вышло']) < 8:
            примеры.append({'инн': str(r['inn']), 'было': стар[:50],
                            'стало': нов, 'итог': чем})
    if применять:
        ts = time.strftime('%Y-%m-%dT%H:%M:%S')
        сделано = 0
        for инн, стар, нов, чем in правки:
            try:
                c.execute("UPDATE emails SET email=?, "
                          "pometka=trim(coalesce(pometka,'')||?), "
                          "updated_at=? WHERE inn=? AND email=?",
                          (нов, ' почин:' + чем, ts, инн, стар))
                c.execute("UPDATE companies SET best_email=? WHERE inn=? AND best_email=?",
                          (нов, инн, стар))
                сделано += 1
            except sqlite3.IntegrityError:
                # такой адрес у компании уже есть — битый дубль убираем
                c.execute('DELETE FROM emails WHERE inn=? AND email=?', (инн, стар))
                c.execute("UPDATE companies SET best_email=? WHERE inn=? AND best_email=?",
                          (нов, инн, стар))
                сделано += 1
        c.commit()
        итог['записано'] = сделано
        with open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
            for инн, стар, нов, чем in правки:
                f.write(json.dumps({'inn': инн, 'было': стар, 'стало': нов,
                                    'чем': чем, 'ts': ts}, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
    c.close()
    итог['примеры'] = примеры
    return итог


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    и = разбор('--primenit' in sys.argv)
    прим = и.pop('примеры', [])
    print(json.dumps({'примеры': прим}, ensure_ascii=False, indent=1))
    print(json.dumps(и, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
