# -*- coding: utf-8 -*-
"""Стадия и нормализованная дата - в enrich.db, рядом с signals, тем же способом, что новости.

Владелец: «в бд как новости складываются так же». Поэтому не файл в _ops, а таблица в той же
`C:\\sender\\enrich.db`, в стиле остальных таблиц базы (TEXT-поля, updated_at, INSERT OR
REPLACE по ключу, индексы на то, по чему будем спрашивать).

Таблица `signal_stadiya` - один к одному со строкой `signals` (ключ - её rowid):

    rid                  rowid строки signals (ключ)
    inn, source_url      чтобы строка читалась и без джойна
    data_iso             дата события в ISO, единая для всех источников
    data_otkuda          karta_vk | karta | rss | url | tekst  - ОТКУДА эта дата
    data_vzyatiya        когда МЫ её взяли (seen_news/updated_at) - НЕ дата события
    data_vzyatiya_otkuda seen_news | updated_at
    data_plana           срок из текста, если он в будущем («запустят в 2027»)
    prichina_bez_daty    словами, если даты нет
    stadiya, nomer_stadii, uverennost, zacepka, otrasl
    status               ok | ne_opredelit | sboy_provaydera | net_v_otvete
    vydumka              модель сочла текст выдуманным
    model, updated_at

ГЛАВНОЕ НАЗНАЧЕНИЕ - новый поток: `obrabotat_sobytie(...)` вызывается на ОДНОМ событии
сразу после `add_signal`, и событие получает дату и стадию в момент попадания в базу, а не
раскопками через месяц.

Запуск:
    3s_sobytie_v_bazu.py --sozdat                       создать таблицу
    3s_sobytie_v_bazu.py --zagruzit 3s_progon60.jsonl   влить результат испытания с дропа
    3s_sobytie_v_bazu.py --odno "текст события"         одиночный путь (проверка на сервере)
    3s_sobytie_v_bazu.py --pokazat 15                   прочитать записанное обратно
"""
import argparse
import datetime
import importlib.util
import json
import os
import sqlite3
import sys
import urllib.request

DIR = os.path.dirname(os.path.abspath(__file__))
BAZA = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')


def _modul(imya):
    """Модули лежат рядом и могут называться `3s_sobytie_data.py` - имя с цифры,
    обычным import не берётся."""
    for kandidat in (imya + '.py', '3s_' + imya + '.py'):
        put = os.path.join(DIR, kandidat)
        if os.path.exists(put):
            spec = importlib.util.spec_from_file_location(imya, put)
            m = importlib.util.module_from_spec(spec)
            sys.modules[imya] = m
            spec.loader.exec_module(m)
            return m
    raise ImportError('не найден модуль %s рядом с %s' % (imya, DIR))


SD = _modul('sobytie_data')
SS = _modul('sobytie_stadiya')

SOZDANIE = """
CREATE TABLE IF NOT EXISTS signal_stadiya(
  rid INTEGER PRIMARY KEY,
  inn TEXT, source_url TEXT,
  data_iso TEXT, data_otkuda TEXT, data_tochnost TEXT,
  data_vzyatiya TEXT, data_vzyatiya_otkuda TEXT,
  data_plana TEXT, prichina_bez_daty TEXT,
  stadiya TEXT, nomer_stadii INTEGER, uverennost TEXT, zacepka TEXT, otrasl TEXT,
  status TEXT, vydumka INTEGER DEFAULT 0,
  model TEXT, updated_at TEXT)
"""
INDEKSY = ['CREATE INDEX IF NOT EXISTS ix_stad_stadiya ON signal_stadiya(stadiya)',
           'CREATE INDEX IF NOT EXISTS ix_stad_data ON signal_stadiya(data_iso)',
           'CREATE INDEX IF NOT EXISTS ix_stad_inn ON signal_stadiya(inn)',
           'CREATE INDEX IF NOT EXISTS ix_stad_nomer ON signal_stadiya(nomer_stadii)']

POLYA = ['rid', 'inn', 'source_url', 'data_iso', 'data_otkuda', 'data_tochnost', 'data_vzyatiya',
         'data_vzyatiya_otkuda', 'data_plana', 'prichina_bez_daty', 'stadiya',
         'nomer_stadii', 'uverennost', 'zacepka', 'otrasl', 'status', 'vydumka',
         'model', 'updated_at']


def otkryt(put=None, sekund=60):
    """База ЖИВАЯ: по ней одновременно работают конвейер новостей, панель и соседние
    сессии. Первый заход сюда упал через 60 с на «database is locked» - это не поломка
    прибора, а занятый писатель. Поэтому ждём долго и повторяем, а не падаем."""
    cx = sqlite3.connect(put or BAZA, timeout=sekund)
    cx.execute('PRAGMA busy_timeout=%d' % (sekund * 1000))
    try:
        jm = cx.execute('PRAGMA journal_mode').fetchone()[0]
        # замер 16.09: журнал wal, то есть «database is locked» здесь - это ДЛИННЫЙ чужой
        # писатель (конвейер/панель/соседняя сессия), а не режим журнала. Ждать и повторять.
        print('журнал базы: %s' % jm, file=sys.stderr)
    except Exception:  # noqa: BLE001
        pass
    return cx


def poterpet(fn, popytok=8, pauza=10):
    """Повторить операцию записи, пока база занята. Возвращает результат или бросает."""
    import time
    posled = None
    for i in range(popytok):
        try:
            return fn()
        except sqlite3.OperationalError as ex:
            if 'locked' not in str(ex) and 'busy' not in str(ex):
                raise
            posled = ex
            print('  база занята (%s), попытка %d/%d, ждём %d с'
                  % (ex, i + 1, popytok, pauza), file=sys.stderr)
            time.sleep(pauza)
    raise posled


def sozdat(cx):
    def _s():
        cx.execute(SOZDANIE)
        # таблица могла быть создана раньше, без более поздних колонок: добавляем недостающие
        est = {r[1] for r in cx.execute('PRAGMA table_info(signal_stadiya)')}
        for pole in POLYA:
            if pole not in est:
                cx.execute('ALTER TABLE signal_stadiya ADD COLUMN %s TEXT' % pole)
        for i in INDEKSY:
            cx.execute(i)
        cx.commit()
    poterpet(_s)


def zapisat(cx, rec):
    """INSERT OR REPLACE по rid. Строку без rid не пишем: без ключа она не найдётся
    обратно, а «записал в никуда» выглядит как успех."""
    if not rec.get('rid'):
        return False
    rec.setdefault('updated_at', datetime.datetime.now().replace(microsecond=0).isoformat())

    def _z():
        cx.execute('INSERT OR REPLACE INTO signal_stadiya(%s) VALUES(%s)'
                   % (','.join(POLYA), ','.join('?' * len(POLYA))),
                   [rec.get(p) if not isinstance(rec.get(p), bool) else int(rec.get(p))
                    for p in POLYA])
        cx.commit()
    poterpet(_z)
    return True


def zapisat_mnogo(cx, recs):
    """Заливка пачкой в ОДНОЙ транзакции.

    Построчный commit на живой базе - дорогая ошибка: 60 строк это 60 отдельных
    транзакций, каждая из которых конкурирует с чужим длинным писателем. Замер 16.09:
    построчная заливка съела восемь попыток по 10 с и умерла на «database is locked»,
    хотя те же 60 строк одной транзакцией проходят за миг.
    """
    gotovo = []
    for rec in recs:
        if not rec.get('rid'):
            continue
        rec.setdefault('updated_at', datetime.datetime.now().replace(microsecond=0).isoformat())
        gotovo.append([rec.get(p) if not isinstance(rec.get(p), bool) else int(rec.get(p))
                       for p in POLYA])

    def _z():
        cx.executemany('INSERT OR REPLACE INTO signal_stadiya(%s) VALUES(%s)'
                       % (','.join(POLYA), ','.join('?' * len(POLYA))), gotovo)
        cx.commit()
    poterpet(_z)
    return len(gotovo)


def naydti_rid(cx, inn, source_url, what):
    """rowid только что вставленного сигнала. add_signal делает INSERT OR IGNORE и rowid не
    возвращает, поэтому ищем по той же тройке, по которой сигнал и опознаётся."""
    r = cx.execute('SELECT rowid FROM signals WHERE inn=? AND source_url=? AND what=? '
                   'ORDER BY rowid DESC LIMIT 1', (str(inn or ''), source_url or '',
                                                   what or '')).fetchone()
    return r[0] if r else None


def obrabotat_sobytie(cx, inn='', source='', source_url='', what='', published='',
                      vk_epoch=None, updated_at='', seen_ts='', rid=None,
                      model='claude-fable-5', attempts=3):
    """ВХОД НОВОГО ПОТОКА: одно событие -> дата + стадия + запись в базу.

    Вызывать сразу после add_signal. `published` - это тот самый item['pubDate'],
    который сейчас у четырёх коллекторов пустой; `vk_epoch` - дата поста ВК (p['date']),
    которую col_vk берёт для проверки свежести и выбрасывает.
    """
    d = SD.normalizovat(ts=published, source_url=source_url, what=what, source=source,
                        vk_epoch=vk_epoch, vzyatie=updated_at, seen_ts=seen_ts)
    st = SS.stadiya_odnogo(what, model=model, attempts=attempts)
    if rid is None:
        rid = naydti_rid(cx, inn, source_url, what)
    rec = {'rid': rid, 'inn': inn, 'source_url': source_url, 'model': model,
           'data_iso': d['data_iso'], 'data_otkuda': d['data_otkuda'],
           'data_tochnost': d.get('data_tochnost', ''),
           'data_vzyatiya': d['data_vzyatiya'], 'data_vzyatiya_otkuda': d['data_vzyatiya_otkuda'],
           'data_plana': d['data_plana'], 'prichina_bez_daty': d['prichina_bez_daty'],
           'stadiya': st.get('stadiya', ''), 'nomer_stadii': st.get('nomer_stadii', 0),
           'uverennost': st.get('uverennost', ''), 'zacepka': st.get('zacepka', ''),
           'otrasl': st.get('otrasl', ''), 'status': st.get('status', ''),
           'vydumka': int(bool(st.get('vydumka')))}
    zapisat(cx, rec)
    return rec


def _skachat_s_dropa(imya, kuda):
    url = (os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
           + '/' + imya)
    bez_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    with bez_proxy.open(req, timeout=180) as r:
        dannye = r.read()
    open(kuda, 'wb').write(dannye)
    return len(dannye)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--sozdat', action='store_true')
    p.add_argument('--zagruzit', default='')
    p.add_argument('--odno', default='')
    p.add_argument('--pokazat', type=int, default=0)
    p.add_argument('--baza', default=BAZA)
    a = p.parse_args()
    cx = otkryt(a.baza)
    print('база: %s' % a.baza)

    if a.sozdat:
        sozdat(cx)
        print('таблица signal_stadiya готова')

    if a.zagruzit:
        put = os.path.join(DIR, os.path.basename(a.zagruzit))
        if not os.path.exists(put):
            n = _skachat_s_dropa(os.path.basename(a.zagruzit), put)
            print('скачано с дропа: %s (%d байт)' % (put, n))
        sozdat(cx)
        vsego = 0
        pachka = []
        for line in open(put, encoding='utf-8'):
            if not line.strip():
                continue
            r = json.loads(line)
            vsego += 1
            rec = {'rid': r.get('rid'), 'inn': r.get('inn'), 'source_url': r.get('source_url'),
                   'data_iso': r.get('data_iso'), 'data_otkuda': r.get('data_otkuda'),
                   'data_tochnost': r.get('data_tochnost'),
                   'data_vzyatiya': r.get('data_vzyatiya'),
                   'data_vzyatiya_otkuda': r.get('data_vzyatiya_otkuda'),
                   'data_plana': r.get('data_plana'),
                   'prichina_bez_daty': r.get('prichina_bez_daty'),
                   'stadiya': r.get('st_stadiya'), 'nomer_stadii': r.get('st_nomer_stadii') or 0,
                   'uverennost': r.get('st_uverennost'), 'zacepka': r.get('st_zacepka'),
                   'otrasl': r.get('st_otrasl'), 'status': r.get('st_status'),
                   'vydumka': int(bool(r.get('st_vydumka'))), 'model': 'claude-fable-5'}
            pachka.append(rec)
        zapisano = zapisat_mnogo(cx, pachka)
        print('влито строк: %d из %d (одной транзакцией)' % (zapisano, vsego))

    if a.odno:
        # одиночный путь на сервере: провайдер тут зовётся через verify_company
        sozdat(cx)
        r = SS.stadiya_odnogo(a.odno)
        print('ОДНО СОБЫТИЕ: статус=%s стадия=%r уверенность=%s отрасль=%s выдумка=%s'
              % (r.get('status'), r.get('stadiya'), r.get('uverennost'),
                 r.get('otrasl'), r.get('vydumka')))
        print('  зацепка: %s' % (r.get('zacepka') or '')[:120])
        if r.get('oshibka'):
            print('  ошибка: %s' % r['oshibka'][:200])
        pr = SS.PRIMANKI[0][1]
        rp = SS.stadiya_odnogo(pr)
        print('КОНТРОЛЬ выдуманным текстом на сервере: статус=%s стадия=%r уверенность=%s'
              % (rp.get('status'), rp.get('stadiya'), rp.get('uverennost')))

    if a.pokazat:
        n = cx.execute('SELECT COUNT(*) FROM signal_stadiya').fetchone()[0]
        print('\nв signal_stadiya строк: %d' % n)
        for r in cx.execute('SELECT rid, data_iso, data_otkuda, stadiya, uverennost, otrasl, '
                            'status FROM signal_stadiya ORDER BY rid LIMIT ?', (a.pokazat,)):
            print('  rid=%-6s %-11s %-9s %-15s %-8s %-20s %s'
                  % (r[0], r[1] or '-', r[2] or '-', r[3] or '-', r[4] or '-', r[5] or '-', r[6]))
        print('\nраспределение по стадиям в таблице:')
        for r in cx.execute('SELECT nomer_stadii, stadiya, COUNT(*) FROM signal_stadiya '
                            "WHERE status='ok' GROUP BY 1,2 ORDER BY 1"):
            print('  %s %-16s %d' % (r[0], r[1], r[2]))
        r = cx.execute("SELECT COUNT(*) FROM signal_stadiya WHERE nomer_stadii BETWEEN 1 AND 3 "
                       "AND status='ok'").fetchone()[0]
        print('  три самые ранние стадии: %d' % r)
        r = cx.execute("SELECT COUNT(*) FROM signal_stadiya WHERE data_iso<>''").fetchone()[0]
        print('  строк с датой: %d' % r)
    cx.close()
