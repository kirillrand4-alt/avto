# -*- coding: utf-8 -*-
"""Спасение сайтов-кандидатов вторым признаком — и ЗАМЕР этого признака, а не вера в него.

Поиск сайтов признаёт сайт своим, только если на его страницах нашёлся ИНН. Замер по журналу:
подтверждено по ИНН 33, а в кандидатах застряло 290. Кандидат — это сайт, найденный в выдаче,
но не опубликовавший ИНН; для мелкого завода это норма, а не признак чужого сайта. Крауler
кандидатов не берёт, значит 290 предприятий остаются без обхода на пустом месте.

Второй признак: РЕДКОЕ слово из названия + ГОРОД из ЕГРЮЛ, оба на одной странице сайта.
Частые слова («завод», «комбинат», «групп») выброшены — на них слипается что угодно.

ЧЕСТНАЯ ПРОВЕРКА ПРИЗНАКА (иначе это гадание):
  * чувствительность — гоняем признак по 33 сайтам, УЖЕ подтверждённым по ИНН. Сколько он
    узнаёт из заведомо своих;
  * ложные срабатывания — те же компании подставляем к ЧУЖИМ сайтам (сдвиг списка на 1).
    Сколько раз признак скажет «своё» про заведомо чужое.
Без второго числа первое ничего не значит.
"""
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ЧАСТЫЕ = {'завод', 'комбинат', 'групп', 'группа', 'компания', 'холдинг', 'предприятие',
          'производственный', 'промышленный', 'научный', 'центр', 'сервис', 'торговый',
          'management', 'город', 'район', 'область', 'республика', 'край', 'филиал',
          'управление', 'обьединение', 'объединение', 'корпорация', 'фирма', 'имени'}
ПУТИ = ('', '/contacts/', '/contacts', '/kontakty/', '/kontakty', '/about/', '/o-kompanii/',
        '/rekvizity/', '/requisites/')


def качать(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        return urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8', 'replace')
    except Exception:  # noqa: BLE001
        return ''


def слова(имя):
    """Редкие значащие слова названия — по ним и опознаём."""
    ток = re.findall(r'[А-Яа-яЁёA-Za-z]{5,}', (имя or '').lower())
    return [t for t in ток if t not in ЧАСТЫЕ]


def текст_сайта(сайт):
    осн = сайт.rstrip('/')
    with ThreadPoolExecutor(max_workers=len(ПУТИ)) as пул:
        куски = list(пул.map(lambda p: качать(осн + p), ПУТИ))
    h = ' '.join(куски).lower()
    return re.sub(r'<[^>]+>', ' ', h)


def признак(сайт, имя, город, кэш=None):
    """Возвращает (своё: bool, что_совпало: str). Нужны ОБА сигнала."""
    t = кэш if кэш is not None else текст_сайта(сайт)
    if not t:
        return False, 'страницы не скачались'
    сл = слова(имя)
    нашлось = [w for w in сл if w[:7] in t]
    г = (город or '').lower().strip()
    г_ядро = re.sub(r'^(г\.?|город)\s*', '', г).strip()
    город_есть = bool(г_ядро) and len(г_ядро) >= 4 and g_in(г_ядро, t)
    if нашлось and город_есть:
        return True, f'имя «{нашлось[0]}» + город «{г_ядро}»'
    if нашлось:
        return False, f'только имя «{нашлось[0]}», города нет'
    return False, 'имени нет на сайте'


def g_in(г, t):
    return г[:6] in t


def main():
    журнал = json.load(open(sys.argv[1], encoding='utf-8'))
    карта = json.load(open(sys.argv[2], encoding='utf-8'))
    подтв = [r for r in журнал if r.get('сайт') and r.get('инн_на_странице')]
    канд = [r for r in журнал if r.get('сайт') and not r.get('инн_на_странице')]
    print(f'подтверждённых по ИНН {len(подтв)}, кандидатов {len(канд)}', flush=True)

    def проба(r, сайт_чужой=None):
        инн = r['инн']
        c = карта.get(инн) or {}
        сайт = сайт_чужой or r['сайт']
        ок, поч = признак(сайт, c.get('name') or r.get('имя') or '', c.get('gorod') or '')
        return инн, ок, поч

    with ThreadPoolExecutor(max_workers=8) as пул:
        чувств = list(пул.map(lambda r: проба(r), подтв))
    узнал = sum(1 for _, ок, _ in чувств if ок)
    print(f'ЧУВСТВИТЕЛЬНОСТЬ: признак узнал {узнал} из {len(подтв)} заведомо своих', flush=True)

    сдвиг = [(подтв[i], подтв[(i + 1) % len(подтв)]['сайт']) for i in range(len(подтв))]
    with ThreadPoolExecutor(max_workers=8) as пул:
        ложь = list(пул.map(lambda p: проба(p[0], p[1]), сдвиг))
    лп = sum(1 for _, ок, _ in ложь if ок)
    print(f'ЛОЖНЫЕ СРАБАТЫВАНИЯ: сказал «своё» про чужой сайт {лп} раз из {len(сдвиг)}', flush=True)

    if len(подтв) and лп / max(1, len(сдвиг)) > 0.15:
        print('признак слишком грязный — кандидатов НЕ спасаю', flush=True)
        json.dump({'otkaz': True, 'chuvstv': узнал, 'lozhnyh': лп},
                  open('/home/user/work/kandidaty-itog.json', 'w', encoding='utf-8'),
                  ensure_ascii=False)
        return
    with ThreadPoolExecutor(max_workers=8) as пул:
        рез = list(пул.map(lambda r: проба(r), канд))
    спас = [{'inn': i, 'sayt': r['сайт'], 'pochemu': p}
            for (i, ок, p), r in zip(рез, канд) if ок]
    print(f'СПАСЕНО кандидатов: {len(спас)} из {len(канд)}', flush=True)
    json.dump({'chuvstv': узнал, 'iz': len(подтв), 'lozhnyh': лп, 'spaseno': спас},
              open('/home/user/work/kandidaty-itog.json', 'w', encoding='utf-8'), ensure_ascii=False)


if __name__ == '__main__':
    main()
