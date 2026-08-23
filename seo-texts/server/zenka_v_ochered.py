# -*- coding: utf-8 -*-
r"""Кого сайт не пустил — вернуть в очередь Зенки.

Владелец 21.08: «те, где не удалось открыть сайт или в процессе обхода он был
не открыт, отправь в очередь». Таких три вида, и путать их нельзя:

  1. КЭШ ПУСТ — файл кэша есть, а страниц в нём нет: сайт не отдал ничего
     (защита, таймаут, домен не отвечает). В файле рядом лежат отказы Зенки —
     по ним видно, что именно случилось;
  2. РАЗБОР БЕЗ СТРАНИЦ — в site_facts стоит «страниц в кэше нет»: разбор
     подошёл раньше обхода либо обход не дал ничего;
  3. НЕ ОБХОДИЛИ ВОВСЕ — сайт у компании известен, а в кэше её нет и в очереди
     тоже: до неё просто не дошли.

Кого НЕ возвращаем: площадки и справочники (мерка ploshchadki), компании с
приговором verified=mismatch (сайт чужой — обходить его смысла нет), уже
стоящих в очереди и уже имеющих паспорт нового формата.

    kandidaty()          посчитать и показать, ничего не меняя
    dopisat(predel)      дописать в ochered.txt
"""
import gzip
import json
import os
import sqlite3
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, r'C:\sender', r'C:\sender\server'):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import zenno_most as ZM  # noqa: E402

ZENNO = ZM.ZENNO
OCHERED = ZM.OCHERED
GOTOVO = ZM.GOTOVO
KESH = ZM.KESH
BD = ZM.BD
ОТЧЁТ = r'C:\sender\_ops\zenka_v_ochered.json'


def _в_очереди():
    инн = set()
    if not os.path.exists(OCHERED):
        return инн
    with open(OCHERED, encoding='utf-8', errors='replace') as f:
        for s in f:
            s = s.strip()
            if s:
                инн.add(s.split(';')[0].strip())
    return инн


def _в_gotovo():
    инн = set()
    try:
        with os.scandir(GOTOVO) as it:
            for e in it:
                и = e.name.split('.')[0].split('_')[0]
                if и.isdigit():
                    инн.add(и)
    except OSError:
        pass
    return инн


def _пустые_кэша():
    """{инн: причина} — файл кэша есть, а страниц в нём нет."""
    пусто = {}
    try:
        имена = [n for n in os.listdir(KESH) if n.endswith('.json.gz')]
    except OSError:
        return пусто
    for n in имена:
        инн = n.split('.')[0]
        if not инн.isdigit():
            continue
        try:
            with gzip.open(os.path.join(KESH, n), 'rb') as f:
                д = json.loads(f.read().decode('utf-8', 'replace'))
        except Exception:  # noqa: BLE001
            пусто[инн] = 'кэш битый'
            continue
        есть = any((p.get('html') or '').strip() for p in (д.get('pages') or []))
        if есть:
            continue
        отк = д.get('otkazy') or []
        пусто[инн] = (str(отк[0])[:70] if отк else 'страниц нет, отказов нет')
    return пусто


def kandidaty(predel=None):
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True,
                        timeout=60)
    c.row_factory = sqlite3.Row
    сайты, чужие = {}, set()
    for r in c.execute("select inn, coalesce(site,'') s, coalesce(cand_site,'') cs, "
                       "coalesce(verified,'') v from companies"):
        и = str(r['inn'])
        if r['v'] == 'mismatch':
            чужие.add(и)
            continue
        u = (r['s'] or r['cs']).strip()
        if u:
            сайты[и] = u
    готовы = {str(r[0]) for r in c.execute(
        "select inn from site_facts where coalesce(facts_json,'')<>'' "
        'and coalesce(format,0)>=2')}
    без_страниц = {str(r[0]) for r in c.execute(
        "select inn from site_facts where coalesce(note,'')='страниц в кэше нет'")}
    c.close()

    в_очереди = _в_очереди()
    в_готово = _в_gotovo()
    пустые = _пустые_кэша()
    в_кэше = set()
    try:
        в_кэше = {n.split('.')[0] for n in os.listdir(KESH)
                  if n.endswith('.json.gz')}
    except OSError:
        pass

    причины = {}

    def _добавить(инн, причина):
        if инн in причины or инн in чужие or инн in в_очереди or инн in в_готово:
            return
        if инн in готовы:
            return                       # паспорт уже собран — обходить незачем
        u = сайты.get(инн)
        if not u:
            return                       # некуда идти
        if ZM._ploshchadka(u):
            return                       # справочник или витрина, не сайт компании
        причины[инн] = (причина, u)

    for инн, причина in пустые.items():
        _добавить(инн, 'кэш пуст: ' + причина)
    for инн in без_страниц:
        _добавить(инн, 'разбор: страниц в кэше нет')
    for инн in сайты:
        if инн not in в_кэше:
            _добавить(инн, 'не обходили вовсе')

    сводка = {'всего': len(причины), 'по_видам': {}}
    for _и, (причина, _u) in причины.items():
        вид = причина.split(':')[0]
        сводка['по_видам'][вид] = сводка['по_видам'].get(вид, 0) + 1
    сводка['примеры'] = [{'инн': и, 'сайт': u[:44], 'почему': п[:70]}
                         for и, (п, u) in list(причины.items())[:8]]
    сводка['отсев'] = {'чужой сайт (mismatch)': len(чужие),
                       'уже в очереди': len(в_очереди),
                       'ждут разбора в gotovo': len(в_готово)}
    if predel:
        отобрано = dict(list(причины.items())[:int(predel)])
    else:
        отобрано = причины
    return сводка, отобрано


def dopisat(predel=None):
    сводка, отобрано = kandidaty(predel)
    if not отобрано:
        сводка['дописано'] = 0
        return сводка
    # ОДНОЙ ЗАПИСЬЮ И С fsync: очередь читает чужой процесс, дописывать её
    # по строчке — значит однажды дать ему полстроки.
    строки = ''.join('%s;%s;oba\n' % (и, u) for и, (_п, u) in отобрано.items())
    with open(OCHERED, 'a', encoding='utf-8') as f:
        f.write(строки)
        f.flush()
        os.fsync(f.fileno())
    сводка['дописано'] = len(отобрано)
    сводка['когда'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    try:
        os.makedirs(os.path.dirname(ОТЧЁТ), exist_ok=True)
        with open(ОТЧЁТ, 'w', encoding='utf-8') as f:
            json.dump({'сводка': сводка,
                       'инн': {и: п for и, (п, _u) in отобрано.items()}},
                      f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
    except Exception:  # noqa: BLE001
        pass
    return сводка


def main():
    а = sys.argv[1:]
    предел = int(а[а.index('--predel') + 1]) if '--predel' in а else None
    if '--primenit' in а:
        print(json.dumps(dopisat(предел), ensure_ascii=False, indent=1))
    else:
        сводка, _ = kandidaty(предел)
        print(json.dumps(сводка, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
