# -*- coding: utf-8 -*-
r"""Дожать проверку адресов партии, переживая перезаписи задания панелью.

Найдено 18.08. Штатный цикл панели (probe_sync.опубликовать) кладёт на дроп
задание ЦЕЛИКОМ — PUT, а не дописывание, — и берёт в него только адреса очереди
подтверждения. Наши 666 адресов партии, отданные через «срочно», прожили на
дропе меньше десяти минут: следующий круг цикла записал поверх три адреса
очереди. Работник (задача ProbeWorker на VPS, раз в 10 минут по 60 адресов) их
просто не увидел.

Здесь дожимаем без правки панели и без перезапуска службы: раз в три минуты
СЛИВАЕМ задание — то, что лежит на дропе, плюс наши непроверенные, — и кладём
обратно. Что бы панель ни записала, через три минуты наши адреса снова в файле,
а очередь подтверждения при этом не теряется.

Останавливаемся, когда у всех адресов группы есть вердикт, или по пределу часов.

    python probe_dozhim.py "Партия 935" [часов]
"""
import json
import os
import sqlite3
import subprocess
import sys
import time

БД = r'C:\sender\sender.db'
СЕКРЕТЫ = r'C:\sender\server\runner-secrets.env'
ЗАДАНИЕ = 'probe-zadanie.json'
ПАУЗА = 180


def _ключи():
    env = {}
    with open(СЕКРЕТЫ, encoding='utf-8', errors='replace') as f:
        for l in f:
            if '=' in l and not l.strip().startswith('#'):
                k, v = l.split('=', 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env['DROP_URL'].rstrip('/'), env['DROP_TOKEN']


def _дроп(метод, имя, данные=None):
    url, tok = _ключи()
    цель = '%s/%s' % (url, имя)
    к = ['curl', '-s', '-H', 'X-Drop-Token: ' + tok]
    if метод == 'PUT':
        к += ['-X', 'PUT', '--data-binary', '@-', цель]
        p = subprocess.run(к, input=данные, capture_output=True, text=True, timeout=180)
    else:
        к += [цель]
        p = subprocess.run(к, capture_output=True, text=True, timeout=180)
    return p.stdout or ''


def остаток(группа):
    s = sqlite3.connect('file:%s?mode=ro' % БД.replace('\\', '/'), uri=True)
    # «Неясно» — не вердикт об адресе, а обстоятельства пробы (серый список,
    # обрыв связи). Такие переспрашиваем: работник на VPS их забыл по нашей
    # команде, и следующий его проход проверит их заново.
    верд = {str(r[0]).lower() for r in s.execute(
        "select email from addr_probe where coalesce(verdict,'') <> 'неясно'")}
    из = []
    for em, ex in s.execute("select lower(coalesce(email,'')), coalesce(extra_json,'') "
                            'from recipients where extra_json like ?',
                            ('%' + группа + '%',)):
        if not em or em in верд:
            continue
        try:
            d = json.loads(ex) if ex.strip() else {}
        except Exception:  # noqa: BLE001
            continue
        if группа in [str(g) for g in (d.get('gruppy') or [])]:
            из.append(em)
    s.close()
    return sorted(set(из)), верд


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    группа = sys.argv[1] if len(sys.argv) > 1 else 'Партия 935'
    часов = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0
    до = time.time() + часов * 3600
    круг = 0
    while time.time() < до:
        круг += 1
        наши, верд = остаток(группа)
        if not наши:
            print('%s все адреса группы получили вердикт, кругов %d'
                  % (time.strftime('%H:%M:%S'), круг), flush=True)
            return 0
        было = []
        try:
            r = json.loads(_дроп('GET', ЗАДАНИЕ) or '[]')
            было = r.get('emails') if isinstance(r, dict) else r
            было = [str(x).strip().lower() for x in (было or [])]
            # выкидываем уже проверенные: работник их всё равно пропустит, а
            # файл пухнет и по нему не видно настоящего остатка
            было = [x for x in было if x not in верд]
        except Exception:  # noqa: BLE001  задания нет — не беда
            было = []
        # ПОРЯДОК РЕШАЕТ. У работника стоит --per-domain 3: за проход он берёт
        # первые 60 адресов задания и проверяет не больше трёх на один домен.
        # Наш остаток — сплошь mail.ru и yandex.ru, и голова задания оказалась
        # забита одним доменом: вместо шестидесяти проверок за проход шло три.
        # Поэтому раскладываем вперемешку — по одному адресу с домена по кругу:
        # тогда первые 60 это 60 разных доменов и ни один лимит не срабатывает.
        # Очередь подтверждения идёт ПЕРВОЙ: по ней письма уходят сейчас.
        # Перемешиваем ВЕСЬ список, а не только наш хвост: лимит на домен бьёт
        # и по адресам очереди — их в задании оказалось 141, тоже сплошь mail.ru,
        # и они точно так же стояли колом. Внутри домена очередь идёт первой:
        # по ней письма уходят сейчас.
        видели, по_домену, порядок = set(), {}, []
        for a in было + наши:
            if not a or a in видели:
                continue
            видели.add(a)
            д = a.rsplit('@', 1)[-1]
            if д not in по_домену:
                по_домену[д] = []
                порядок.append(д)
            по_домену[д].append(a)
        список = []
        while по_домену:
            for д in list(порядок):
                if д not in по_домену:
                    continue
                список.append(по_домену[д].pop(0))
                if not по_домену[д]:
                    del по_домену[д]
        _дроп('PUT', ЗАДАНИЕ, json.dumps(список, ensure_ascii=False))
        print('%s круг %d: наших без вердикта %d, в задании %d'
              % (time.strftime('%H:%M:%S'), круг, len(наши), len(список)), flush=True)
        time.sleep(ПАУЗА)
    print('время вышло, осталось без вердикта: %d' % len(остаток(группа)[0]), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
