# -*- coding: utf-8 -*-
"""Вскрытие молчания: почему `news_scan.extract_event` даёт NULL на всём подряд.

Три вопроса за один заход (задание на сервере одно за раз, пул общий):
  1) как сейчас ходит шлюз ПО ИМЕНИ (замер 17.09 показал: один из двух адресов
     router.cheap с этого сервера мёртв, и попадание в него зависит от порядка DNS);
  2) что именно внутри `extract_event` и что он возвращает на контрольных заголовках -
     причём с ОТКЛЮЧЁННЫМ голым `except`, чтобы увидеть настоящее исключение;
  3) сырьё: какие таблицы держат материалы, сколько их и за какие даты; последние N
     выкладываются на дроп, чтобы разбор можно было увести в песочницу.

Прибор ТОЛЬКО читает: ни одной записи в базу, серверные файлы не правятся.
"""
import inspect
import json
import os
import re
import sqlite3
import sys
import textwrap
import time
import traceback

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')

LOG = []
BAZA = r'C:\sender\enrich.db'


def skazat(s):
    LOG.append(str(s))
    print(s, flush=True)


def na_drop(imya, telo):
    url = os.environ.get('DROP_URL') or 'https://parsercompressor.online/drop'
    tok = os.environ.get('DROP_TOKEN') or ''
    if not tok:
        for p in (r'C:\sender\server\runner-secrets.env', r'C:\sender\runner-secrets.env',
                  r'C:\sender\server\.env', r'C:\sender\.env'):
            try:
                for line in open(p, encoding='utf-8', errors='replace'):
                    if line.strip().startswith('DROP_TOKEN='):
                        tok = line.split('=', 1)[1].strip()
                    if line.strip().startswith('DROP_URL='):
                        url = line.split('=', 1)[1].strip()
            except Exception:  # noqa: BLE001
                continue
            if tok:
                break
    if not tok:
        skazat('  ДРОП: токена нет, %s не выложен' % imya)
        return
    try:
        import urllib.request as U
        b = telo.encode('utf-8') if isinstance(telo, str) else telo
        req = U.Request('%s/%s' % (url.rstrip('/'), imya), data=b, method='PUT',
                        headers={'X-Drop-Token': tok})
        with U.urlopen(req, timeout=120) as r:
            skazat('  ДРОП: %s выложен (%d Б), ответ %s' % (imya, len(b), r.status))
    except Exception as ex:  # noqa: BLE001
        skazat('  ДРОП: %s не выложился: %r' % (imya, ex))


# --------------------------------------------------------------- 1. шлюз сейчас
def shlyuz():
    import socket
    skazat('\n### 1. ШЛЮЗ ПРЯМО СЕЙЧАС (по имени, как ходит клиент)')
    poryadok = {}
    for _ in range(10):
        try:
            ai = socket.getaddrinfo('router.cheap', 443, socket.AF_INET, socket.SOCK_STREAM)
            poryadok[ai[0][4][0]] = poryadok.get(ai[0][4][0], 0) + 1
        except Exception as ex:  # noqa: BLE001
            poryadok['dns-сбой'] = poryadok.get('dns-сбой', 0) + 1
        time.sleep(0.1)
    skazat('  getaddrinfo первым адресом: %s' % json.dumps(poryadok, ensure_ascii=False))
    try:
        import verify_company as VC
    except Exception as ex:  # noqa: BLE001
        skazat('  verify_company не импортируется: %r' % (ex,))
        return None
    ok = sboy = 0
    for i in range(3):
        t = time.time()
        try:
            out = VC._provider_call_stdlib('Ответь одним словом: работает')
            ok += 1
            skazat('  штатный вызов %d: ОТВЕТ %r за %.1f с' % (i + 1, (out or '')[:30],
                                                               time.time() - t))
        except Exception as ex:  # noqa: BLE001
            sboy += 1
            skazat('  штатный вызов %d: СБОЙ за %.1f с: %s: %s'
                   % (i + 1, time.time() - t, type(ex).__name__, str(ex)[:110]))
    skazat('  ИТОГ штатного пути: ответ %d, сбой %d из 3' % (ok, sboy))
    return VC


# --------------------------------------------------------------- 2. сам классификатор
def klassifikator(VC):
    skazat('\n### 2. news_scan.extract_event')
    try:
        import news_scan as NS
    except Exception as ex:  # noqa: BLE001
        skazat('  news_scan не импортируется: %r' % (ex,))
        return
    skazat('  файл: %s' % NS.__file__)
    try:
        src = inspect.getsource(NS.extract_event)
    except Exception as ex:  # noqa: BLE001
        skazat('  исходник не читается: %r' % (ex,))
        return
    skazat('  длина исходника: %d строк' % len(src.split('\n')))
    skazat('  --- ИСХОДНИК extract_event ---')
    for i, l in enumerate(src.split('\n'), 1):
        skazat('  %3d| %s' % (i, l[:118]))
    skazat('  --- конец исходника ---')

    # кого он зовёт
    zovet = sorted(set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(', src)))
    svoi = [z for z in zovet if hasattr(NS, z) and callable(getattr(NS, z, None))
            and not z.startswith('_' * 2)]
    skazat('  зовёт из своего модуля: %s' % ', '.join(svoi)[:200])
    for z in svoi:
        if z in ('extract_event',):
            continue
        try:
            s2 = inspect.getsource(getattr(NS, z))
        except Exception:  # noqa: BLE001
            continue
        if 'provider' in s2 or 'PROMPT' in s2 or 'json' in s2:
            skazat('\n  --- %s (%d строк) ---' % (z, len(s2.split('\n'))))
            for l in s2.split('\n')[:60]:
                skazat('    ' + l[:116])

    KONTROL = [
        ('ОАО «Щекиноазот» ввело в эксплуатацию новую установку по производству метанола '
         'мощностью 500 тыс. тонн, инвестиции 20 млрд рублей', 'должно быть событие'),
        ('«Норникель» объявил тендер на поставку центробежных компрессоров для Надеждинского '
         'металлургического завода', 'должно быть событие'),
        ('ЕВРАЗ НТМК завершил модернизацию кислородно-компрессорной станции, ИНН 6623000680',
         'должно быть событие'),
        ('СИБУР начал строительство газоперерабатывающего комплекса в Амурской области',
         'должно быть событие'),
        ('Погода в Москве на выходные: ожидается дождь', 'КОНТРОЛЬ, события быть НЕ должно'),
        ('Курс доллара вырос на 2 рубля', 'КОНТРОЛЬ, события быть НЕ должно'),
    ]
    skazat('\n  --- как extract_event отвечает СЕЙЧАС (со штатным голым except) ---')
    sig = None
    try:
        sig = inspect.signature(NS.extract_event)
        skazat('  сигнатура: extract_event%s' % sig)
    except Exception:  # noqa: BLE001
        pass
    nenul = 0
    for tekst, chto in KONTROL:
        t = time.time()
        try:
            r = NS.extract_event(tekst)
        except TypeError:
            try:
                r = NS.extract_event(tekst, '')
            except Exception as ex:  # noqa: BLE001
                r = 'ВЫЗОВ НЕ СОБРАЛСЯ: %r' % (ex,)
        except Exception as ex:  # noqa: BLE001
            r = 'ИСКЛЮЧЕНИЕ НАРУЖУ: %r' % (ex,)
        if r is not None and not isinstance(r, str):
            nenul += 1
        skazat('  [%s] %-28s -> %s   (%.1f с)'
               % ('событие' if r not in (None,) and not isinstance(r, str) else 'NULL   ',
                  chto[:28], json.dumps(r, ensure_ascii=False)[:90] if not isinstance(r, str)
                  else r[:90], time.time() - t))
    skazat('  непустых ответов: %d из %d' % (nenul, len(KONTROL)))

    # --- тот же прогон, но БЕЗ голого except: нужна настоящая ошибка ---
    skazat('\n  --- тот же вызов с ОТКЛЮЧЁННЫМ голым except (ищем настоящую ошибку) ---')
    telo = textwrap.dedent(src)
    zamena = 0
    novyy_stroki = []
    for l in telo.split('\n'):
        if re.match(r'^(\s*)except Exception:\s*$', l):
            otstup = re.match(r'^(\s*)', l).group(1)
            novyy_stroki.append(otstup + 'except Exception as _vskrytie_ex:')
            novyy_stroki.append(otstup + '    import traceback as _tb; _tb.print_exc()')
            novyy_stroki.append(otstup + '    raise')
            zamena += 1
        elif re.match(r'^(\s*)except Exception as \w+:\s*$', l) and 'return None' in telo:
            novyy_stroki.append(l)
        else:
            novyy_stroki.append(l)
    if not zamena:
        skazat('  голого `except Exception:` в исходнике не нашлось - замена не нужна')
    else:
        skazat('  снято голых except: %d' % zamena)
    kod = '\n'.join(novyy_stroki).replace('def extract_event', 'def extract_event_gromko', 1)
    prostranstvo = dict(NS.__dict__)
    try:
        exec(compile(kod, '<extract_event_gromko>', 'exec'), prostranstvo)
        f = prostranstvo['extract_event_gromko']
    except Exception as ex:  # noqa: BLE001
        skazat('  громкую копию собрать не вышло: %r' % (ex,))
        return
    for tekst, chto in KONTROL[:3] + KONTROL[4:5]:
        t = time.time()
        try:
            r = f(tekst)
            skazat('  [громко] %-28s -> %s (%.1f с)'
                   % (chto[:28], json.dumps(r, ensure_ascii=False)[:100], time.time() - t))
        except TypeError as ex:
            skazat('  [громко] %-28s -> TypeError: %s' % (chto[:28], str(ex)[:100]))
        except Exception as ex:  # noqa: BLE001
            skazat('  [громко] %-28s -> НАСТОЯЩАЯ ОШИБКА %s: %s'
                   % (chto[:28], type(ex).__name__, str(ex)[:130]))
            skazat('      ' + traceback.format_exc().strip().split('\n')[-3][:120])


# --------------------------------------------------------------- 3. сырьё
def syryo(skolko=60):
    skazat('\n### 3. СЫРЬЁ: что лежит в базе')
    try:
        con = sqlite3.connect('file:%s?mode=ro' % BAZA, uri=True)
    except Exception as ex:  # noqa: BLE001
        skazat('  база не открылась: %r' % (ex,))
        return
    cur = con.cursor()
    tabl = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    skazat('  таблиц всего: %d' % len(tabl))
    interes = [t for t in tabl if any(k in t.lower() for k in
                                      ('news', 'signal', 'sob', 'event', 'material', 'post',
                                       'rss', 'feed'))]
    skazat('  похожие на новости: %s' % ', '.join(interes))
    for t in interes:
        try:
            n = cur.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
            cols = [c[1] for c in cur.execute('PRAGMA table_info("%s")' % t)]
            skazat('  %-22s %7d строк | %s' % (t, n, ', '.join(cols)[:96]))
        except Exception as ex:  # noqa: BLE001
            skazat('  %-22s не прочиталась: %r' % (t, ex))

    # свежесть signals
    try:
        for kol in ('ts', 'created_at', 'dt', 'date'):
            try:
                rows = cur.execute('SELECT substr(%s,1,7) m, COUNT(*) FROM signals '
                                   'GROUP BY m ORDER BY m DESC LIMIT 8' % kol).fetchall()
                skazat('  signals по месяцам (%s): %s' % (kol, rows))
                break
            except Exception:  # noqa: BLE001
                continue
    except Exception as ex:  # noqa: BLE001
        skazat('  signals по месяцам не посчитались: %r' % (ex,))

    # выгрузка сырья
    kandidaty = [t for t in interes if t not in ('signals',)]
    vygruzka = []
    for t in kandidaty:
        cols = [c[1] for c in cur.execute('PRAGMA table_info("%s")' % t)]
        tekstovye = [c for c in cols if any(k in c.lower() for k in
                                            ('text', 'tekst', 'title', 'zagolovok', 'body',
                                             'snippet', 'content', 'passage', 'descr', 'url',
                                             'link', 'src', 'source', 'ts', 'date', 'k'))]
        if not tekstovye:
            tekstovye = cols
        try:
            poryadok = 'rowid DESC'
            rows = cur.execute('SELECT %s FROM "%s" ORDER BY %s LIMIT %d'
                               % (', '.join('"%s"' % c for c in tekstovye), t, poryadok,
                                  skolko)).fetchall()
        except Exception as ex:  # noqa: BLE001
            skazat('  выгрузка %s не удалась: %r' % (t, ex))
            continue
        for r in rows:
            d = {c: (v if isinstance(v, (str, int, float, type(None))) else str(v))
                 for c, v in zip(tekstovye, r)}
            d['_tablica'] = t
            vygruzka.append(d)
        skazat('  из %s взято %d строк, колонки %s' % (t, len(rows), tekstovye[:8]))
    if vygruzka:
        obr = json.dumps(vygruzka[:3], ensure_ascii=False)[:600]
        skazat('  образец: %s' % obr)
        na_drop('3s-syryo-novostey.json',
                json.dumps(vygruzka, ensure_ascii=False, indent=1))
    con.close()


if __name__ == '__main__':
    skolko = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 60
    VC = None
    for f, imya in ((shlyuz, 'шлюз'), ):
        try:
            VC = f()
        except Exception:  # noqa: BLE001
            skazat('блок %s упал: %s' % (imya, traceback.format_exc()[-300:]))
    try:
        klassifikator(VC)
    except Exception:  # noqa: BLE001
        skazat('блок классификатора упал: %s' % traceback.format_exc()[-400:])
    try:
        syryo(skolko)
    except Exception:  # noqa: BLE001
        skazat('блок сырья упал: %s' % traceback.format_exc()[-400:])
    na_drop('3s-vskrytie-novostey.txt', '\n'.join(LOG))
    skazat('\n=== вскрытие закончено ===')
