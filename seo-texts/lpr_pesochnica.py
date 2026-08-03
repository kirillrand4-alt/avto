# -*- coding: utf-8 -*-
"""Поиск технических ЛПР по должности — из ПЕСОЧНИЦЫ, в двенадцать потоков.

ЗАЧЕМ ОТДЕЛЬНО ОТ `lpr_serp.py`. Тот модуль пишет через `EnrichDB` и потому исполняется
только на сервере владельца, а там очередь тяжёлых задач однопоточная и рубит задание на
1 800 секундах — за один заход проходит около полутора десятков предприятий. Ключи
XMLRiver владелец разрешил забрать в песочницу 03.08; `xmlriver.com` отсюда отвечает
(проверено живым запросом: 9 результатов, ошибок нет). Значит ту же выдачу можно брать в
двенадцать потоков без потолка, а запись в панель делать потом одним куском.

Логика запроса взята у `lpr_serp` целиком и без изменений — те же роли, тот же разбор
имени компании (аббревиатура губит привязку: 3 доказуемых из 12 против 10 из 12 у полного
имени), тот же отсев мусорных доменов. Здесь только другой транспорт и другой выход.

Пишет построчно в jsonl и продолжает с места остановки.

Запуск:
    python3 lpr_pesochnica.py <celi.csv> [--lim N] [--potokov 12] [--rezhim b|a]
"""
import csv, json, os, re, sys, threading, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

for _l in open('/home/user/work/.keys-3s.env'):
    if '=' in _l:
        _k, _v = _l.strip().split('=', 1)
        os.environ.setdefault(_k, _v)


def _vzyat_iz_lpr_serp():
    """Роли и разбор имени берём ИЗ `lpr_serp.py`, но НЕ импортом.

    Импортировать его нельзя: он тянет `news_scan` и `enrich_db` с `C:\\sender` и в
    песочнице падает на первой же строке. Копировать роли к себе тоже нельзя — два списка
    ролей разъедутся в первый же день, и никто не заметит. Поэтому вытаскиваю нужные куски
    из ИСХОДНИКА по именам и выполняю их в чистом пространстве: источник правды один, а
    серверные зависимости не поднимаются.
    """
    import ast as _ast
    src = open('/home/user/work/lpr_serp.py', encoding='utf-8').read()
    derevo = _ast.parse(src)
    nuzhno = {'РОЛИ', 'ЗАПРОСЫ_A', 'ЗАПРОСЫ_B', '_РОЛЬ_РЕГ', '_МУСОР_ДОМЕН',
              '_ОПФ_НАЧАЛО', '_АББР', 'рег_роли', 'мусорный', 'ядро_имени',
              'имя_для_запроса'}
    kuski = []
    for u in derevo.body:
        imya = getattr(u, 'name', None)
        if imya is None and isinstance(u, _ast.Assign):
            imya = getattr(u.targets[0], 'id', None)
        if imya in nuzhno:
            kuski.append(_ast.get_source_segment(src, u))
    prostranstvo = {'re': re}
    exec('\n'.join(kuski), prostranstvo)  # noqa: S102
    ne_vzyali = nuzhno - set(prostranstvo)
    if ne_vzyali:
        raise RuntimeError(f'в lpr_serp.py не найдено: {sorted(ne_vzyali)}')
    return type('L', (), prostranstvo)


L = _vzyat_iz_lpr_serp()

POTOK = 'lpr-pesochnica.jsonl'
USER, KEY = os.environ['XMLRIVER_USER'], os.environ['XMLRIVER_KEY']
DOC = re.compile(r'<doc>(.*?)</doc>', re.S)
URL = re.compile(r'<url>([^<]*)</url>')
ZAG = re.compile(r'<title>(.*?)</title>', re.S)
TEKST = re.compile(r'<passage>(.*?)</passage>', re.S)
OSHIBKA = re.compile(r'<error[^>]*>([^<]*)')
PEREZAPROS = re.compile(r'перезапрос|повторите|не получен|timeout|таймаут', re.I)


def _bez(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s or '')).strip()


def serp(q, popytok=5):
    """Выдача. Возвращает (документы, ошибка). Ошибка и пустая выдача — РАЗНЫЕ исходы."""
    url = (f'https://xmlriver.com/search/xml?user={USER}&key={KEY}'
           f'&query={urllib.parse.quote(q)}')
    for p in range(popytok):
        try:
            b = urllib.request.urlopen(
                urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}),
                timeout=60).read().decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            if p == popytok - 1:
                return [], f'{type(e).__name__}: {str(e)[:60]}'
            time.sleep(2 * (p + 1))
            continue
        m = OSHIBKA.search(b)
        if m:
            tekst = _bez(m.group(1))
            # «Выполните перезапрос» — это НЕ отказ, это прямое указание сервиса повторить:
            # поисковая система не ответила ЕМУ, а не нам. Первая версия считала его сбоем и
            # шла дальше — на 150 запросах так потерялось 54, то есть 36% выдачи. Повторяем
            # с нарастающей паузой; остальные ошибки (лимит, неверный ключ) повтором не
            # лечатся и возвращаются сразу.
            if PEREZAPROS.search(tekst) and p < popytok - 1:
                time.sleep(3 * (p + 1))
                continue
            return [], f'xmlriver: {tekst[:80]}'
        out = []
        for d in DOC.findall(b):
            u = URL.search(d)
            out.append({'url': u.group(1) if u else '',
                        'zagolovok': _bez((ZAG.search(d) or [None, ''])[1]
                                          if False else (ZAG.search(d).group(1)
                                                         if ZAG.search(d) else '')),
                        'tekst': ' '.join(_bez(x) for x in TEKST.findall(d))[:600]})
        return out, ''
    return [], 'не дошло'


# ФИО рядом с должностью. Ищем в тексте выдачи, а не гадаем: если фамилии в отрывке нет,
# страница всё равно сохраняется — по ней потом ходит обходчик, — но человеком не
# считается. Пустой результат тут значит «в отрывке не назван», а не «его нет».
FIO_POLNOE = re.compile(r'\b([А-ЯЁ][а-яё\-]{2,})\s+([А-ЯЁ][а-яё]{2,})\s+'
                        r'([А-ЯЁ][а-яё]{2,}(?:ович|евич|ьевич|овна|евна|ьевна|ична|инична))\b')
FIO_INIC = re.compile(r'\b([А-ЯЁ][а-яё\-]{2,})\s+([А-ЯЁ]\.\s?[А-ЯЁ]\.)')
IMYA_FAM = re.compile(r'\b([А-ЯЁ]\.\s?[А-ЯЁ]\.)\s?([А-ЯЁ][а-яё\-]{2,})\b')


def lyudi_iz(tekst, zagolovok):
    t = f'{zagolovok} {tekst}'
    naydeno = []
    for m in FIO_POLNOE.finditer(t):
        naydeno.append((f'{m.group(1)} {m.group(2)} {m.group(3)}', 'полное ФИО'))
    for m in FIO_INIC.finditer(t):
        naydeno.append((f'{m.group(1)} {m.group(2)}', 'фамилия с инициалами'))
    for m in IMYA_FAM.finditer(t):
        naydeno.append((f'{m.group(2)} {m.group(1)}', 'фамилия с инициалами'))
    vid = {}
    for f, k in naydeno:
        vid.setdefault(f, k)
    return [{'fio': f, 'vid_imeni': k} for f, k in vid.items()]


def rol_v(tekst, zagolovok):
    t = f'{zagolovok} {tekst}'
    for klyuch, imen, _tv, prio in L.РОЛИ:
        if L._РОЛЬ_РЕГ[klyuch].search(t):
            return klyuch, imen, prio
    return '', '', 0


def main():
    src = sys.argv[1]
    lim = int(sys.argv[sys.argv.index('--lim') + 1]) if '--lim' in sys.argv else 10 ** 9
    pot = int(sys.argv[sys.argv.index('--potokov') + 1]) if '--potokov' in sys.argv else 12
    rezhim = sys.argv[sys.argv.index('--rezhim') + 1] if '--rezhim' in sys.argv else 'b'
    zaprosy = L.ЗАПРОСЫ_B if rezhim == 'b' else L.ЗАПРОСЫ_A

    celi = {}
    for r in csv.DictReader(open(src, encoding='utf-8-sig'), delimiter=';'):
        i = (r.get('inn') or r.get('inn_zakazchika') or '').strip()
        n = (r.get('predpriyatie') or r.get('zakazchik') or '').strip()
        if i and n and i not in celi:
            celi[i] = n
    # СБОЙНАЯ ЗАПИСЬ НЕ СЧИТАЕТСЯ СДЕЛАННОЙ. Иначе перезапуск после отказов выдачи
    # пропускает их как готовые, и потерянное остаётся потерянным навсегда — а это ровно
    # тот случай, когда «ноль» есть отказ прибора. Дубли от двух одновременно запущенных
    # экземпляров тоже схлопываются здесь: 03.08 я убила оболочку вместо процесса, старый
    # прогон продолжил идти рядом с новым, и вдвоём они насытили аккаунт xmlriver —
    # отказы подскочили с 3% до 70%.
    gotovo = set()
    if os.path.exists(POTOK):
        for ln in open(POTOK, encoding='utf-8'):
            try:
                z = json.loads(ln)
                if not z.get('err'):
                    gotovo.add((z['inn'], z['zapros_id']))
            except Exception:  # noqa: BLE001
                pass
    zad = [(i, n, qid, sh) for i, n in list(celi.items())[:lim] for qid, sh in zaprosy
           if (i, qid) not in gotovo]
    print(f'предприятий {len(celi)}, запросов к выдаче {len(zad)} '
          f'(уже сделано {len(gotovo)}), потоков {pot}', file=sys.stderr, flush=True)

    f = open(POTOK, 'a', encoding='utf-8')
    lock = threading.Lock()
    sch = {'n': 0, 'sboev': 0, 'stranic': 0, 'lyudey': 0, 'teh': 0}

    def odin(z):
        inn, imya, qid, shablon = z
        yadro = L.ядро_имени(imya) or imya
        q = shablon.format(n=yadro)
        docs, err = serp(q)
        chisto = [d for d in docs if not L.мусорный(d['url'])]
        lyudi = []
        for d in chisto:
            klyuch, imen, prio = rol_v(d['tekst'], d['zagolovok'])
            if not klyuch:
                continue
            for ch in lyudi_iz(d['tekst'], d['zagolovok']):
                lyudi.append({**ch, 'dolzhnost': imen, 'rol_klyuch': klyuch,
                              'prioritet_roli': prio, 'ssylka': d['url'],
                              'citata': d['tekst'][:300]})
        return {'inn': inn, 'predpriyatie': imya, 'zapros_id': qid, 'zapros': q,
                'err': err, 'stranic': len(chisto), 'lyudi': lyudi}

    with ThreadPoolExecutor(max_workers=pot) as ex:
        for r in ex.map(odin, zad):
            with lock:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
                sch['n'] += 1
                sch['sboev'] += 1 if r['err'] else 0
                sch['stranic'] += r['stranic']
                sch['lyudey'] += len(r['lyudi'])
                sch['teh'] += sum(1 for x in r['lyudi'] if x['prioritet_roli'] == 1)
                if sch['n'] % 50 == 0:
                    f.flush()
                    os.fsync(f.fileno())
                    print(f"  {sch['n']}/{len(zad)} запросов, страниц {sch['stranic']}, "
                          f"людей {sch['lyudey']} (технических {sch['teh']}), "
                          f"сбоев {sch['sboev']}", file=sys.stderr, flush=True)
    f.flush()
    f.close()
    print(f"готово: запросов {sch['n']}, страниц {sch['stranic']}, людей {sch['lyudey']}, "
          f"из них в технических ролях {sch['teh']}, СБОЕВ {sch['sboev']} "
          f"(сбой это не ноль) → {POTOK}", file=sys.stderr)


if __name__ == '__main__':
    main()
