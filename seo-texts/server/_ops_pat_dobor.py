# -*- coding: utf-8 -*-
"""ДОБОР по компаниям, где патентов «не нашлось».

Зачем: у Калужского турбинного завода и Уралхиммаша ноль заведомо ЛОЖНЫЙ —
их патенты я видел глазами в разведке (freepatent 2204022, 2267658 с
патентообладателем ОАО «Калужский турбинный завод»; 2283743 с ОАО «Уральский
завод химического машиностроения» (ОАО «Уралхиммаш»)). Значит ограничитель —
не патентная база, а сколько ссылок отдала выдача. Бьём теми же базами, но
запросами по КАЖДОМУ ключу патентообладателя и с постраничностью, чтобы
отделить «патентов нет» от «выдача не показала».

Пишем отдельным потоком: C:\\sender\\_ops\\pat_dobor.jsonl
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
sys.argv = [sys.argv[0]]          # чтобы импорт не поймал чужие ключи
import _ops_pat_patents as P      # noqa: E402

ПОТОК = r'C:\sender\_ops\pat_dobor.jsonl'
НАЧАЛО = time.time()
БЮДЖЕТ = 200.0

# берём из основного потока тех, у кого своих патентов ноль
ЦЕЛИ = []
осн = r'C:\sender\_ops\pat_patents.jsonl'
пусто = set()
if os.path.exists(осн):
    for ln in io.open(осн, encoding='utf-8', errors='replace'):
        try:
            x = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        if not x.get('свои_патенты'):
            пусто.add(str(x.get('inn')))
for inn, имя, ключи in P.ВЫБОРКА:
    if inn in пусто:
        ЦЕЛИ.append((inn, имя, ключи))
print('добираем компаний:', len(ЦЕЛИ), [i for i, _, _ in ЦЕЛИ])


def сделано():
    было = set()
    if os.path.exists(ПОТОК):
        for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
            try:
                было.add(str(json.loads(ln).get('inn')))
            except Exception:  # noqa: BLE001
                pass
    return было


def добор(inn, имя, ключи):
    out = {'inn': inn, 'имя': имя, 'ссылок': 0, 'прочитано': 0,
           'свои_патенты': [], 'чужих_отсеяно': 0, 'авторы': [], 'примеры': [],
           'обладатели_чужих': []}
    соб = []
    запросы = []
    for k in ключи:
        запросы.append('site:freepatent.ru "%s"' % k)
        запросы.append('site:findpatent.ru "%s"' % k)
    запросы.append('"%s" патент изобретение автор freepatent' % имя)
    for з in запросы:
        for стр in (0, 1):
            if time.time() - НАЧАЛО > БЮДЖЕТ:
                break
            for x in P.выдача(з, стр):
                if P._ПАТСТР.search(x) and x not in соб:
                    соб.append(x)
            time.sleep(0.3)
        if len(соб) >= 16:
            break
    соб = соб[:16]
    out['ссылок'] = len(соб)
    страницы = []
    if соб:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=6) as п:
            страницы = list(п.map(P.читать, соб))
    было = set()
    for u, t, режим, дл in страницы:
        if not t or len(t) < 400:
            continue
        out['прочитано'] += 1
        авторы, обл, сыро = P.разобрать(t)
        да, почему = P.свой(обл, ключи)
        if not да:
            out['чужих_отсеяно'] += 1
            if len(out['обладатели_чужих']) < 4:
                out['обладатели_чужих'].append(обл[:80])
            continue
        out['свои_патенты'].append(u[:90])
        for ч in авторы:
            к = ч.lower().replace('.', '').replace(' ', '')
            if к in было:
                continue
            было.add(к)
            out['авторы'].append(ч)
            if len(out['примеры']) < 6:
                out['примеры'].append({'фио': ч, 'обладатель': обл[:100],
                                       'основание': почему, 'ссылка': u[:90]})
    out['авторов'] = len(out['авторы'])
    return out


def main():
    гот = сделано()
    ф = io.open(ПОТОК, 'a', encoding='utf-8')
    for inn, имя, ключи in ЦЕЛИ:
        if inn in гот:
            continue
        if time.time() - НАЧАЛО > БЮДЖЕТ:
            break
        try:
            r = добор(inn, имя, ключи)
        except Exception as ex:  # noqa: BLE001
            r = {'inn': inn, 'имя': имя,
                 'ошибка': '%s: %s' % (type(ex).__name__, str(ex)[:90])}
        ф.write(json.dumps(r, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())
        print('ДОБОР %-28s ссылок=%d прочит=%d своих=%d чужих=%d авторов=%d %s'
              % (имя[:28], r.get('ссылок', 0), r.get('прочитано', 0),
                 len(r.get('свои_патенты') or []), r.get('чужих_отсеяно', 0),
                 r.get('авторов', 0), r.get('ошибка') or ''))
    ф.close()
    print('ДОБОР: всего %d из %d' % (len(сделано()), len(ЦЕЛИ)))


if __name__ == '__main__':
    main()
