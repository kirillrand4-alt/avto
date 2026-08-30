# -*- coding: utf-8 -*-
r"""Убрать из очереди и из карточек кандидатов, которые сайтами не являются.

ЧТО СЛУЧИЛОСЬ 30.08. Я поставил в начало очереди 1 902 мейеровских кандидата —
977 нетронутых и 925 «не открывшихся». Через час Зенка перестала выдавать
страницы вовсе: она жгла пять ядер и складывала всё в ne_otkrylis. Смотрим
голову очереди:

    gmail.kom, hormail.com, list.rue, maif.ru, es-mail.ru      — описки почтовых
    edu.tatar.ru, aktanysh.tatarstan.ru, azk.tatar.ru          — порталы районов

Это не сайты предприятий. Так выглядит наследство прежнего угадывания сайта по
домену почты: человек написал в анкете «maif.ru» вместо «mail.ru», а конвейер
записал это в cand_site как кандидата. Обходить такое — жечь время впустую и
получать паспорт районной администрации.

ЧТО ДЕЛАЕМ. Отсеиваем по трём признакам: бесплатная почта и её описки (правка
на одну букву), государственные и муниципальные порталы, известные площадки.
Из очереди убираем сразу, из карточек — только по отдельной команде: cand_site
это чужой признак, и стирать его молча нельзя.

    python chistka_kandidatov.py               посчитать
    python chistka_kandidatov.py --ochered     вычистить очередь
    python chistka_kandidatov.py --kartochki   ещё и очистить cand_site
"""
import json
import os
import re
import sqlite3
import sys
import time

ZENNO = os.environ.get('ZENNO_OBMEN', r'C:\seostat\drop\zenno')
ENRICH = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
ЖУРНАЛ = r'C:\sender\server\chistka-kandidatov.jsonl'

ПОЧТОВЫЕ = {'mail.ru', 'yandex.ru', 'ya.ru', 'gmail.com', 'bk.ru', 'list.ru',
            'inbox.ru', 'rambler.ru', 'internet.ru', 'mail.com', 'icloud.com',
            'outlook.com', 'hotmail.com', 'yahoo.com', 'vk.com', 'narod.ru',
            'nm.ru', 'ukr.net', 'yandex.com', 'googlemail.com', 'bk.com'}
# порталы государства и муниципалитетов: за ними стоит администрация, а не завод
ПОРТАЛ = re.compile(
    r'(^|\.)(gov|gosuslugi|nalog|edu|mos|tatarstan|tatar|bashkortostan|admin|'
    r'adm|mo|region|gorod|city|raion|rayon)\.(ru|рф)$|'
    r'\.(gov\.ru|gosuslugi\.ru|tatarstan\.ru|tatar\.ru|bashkortostan\.ru|'
    r'rospotrebnadzor\.ru|mvd\.ru|minzdrav\.gov\.ru)$', re.I)


def _журнал(записи):
    with open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
        for з in записи:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


def _домен(строка):
    d = re.sub(r'^https?://', '', str(строка or '').strip().lower()).split('/')[0]
    return d[4:] if d.startswith('www.') else d


def _правка_на_одну(a, b):
    """Отличаются ли строки одной вставкой, удалением или заменой буквы."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(1 for x, y in zip(a, b) if x != y) == 1
    дл, кор = (a, b) if len(a) > len(b) else (b, a)
    for i in range(len(дл)):
        if дл[:i] + дл[i + 1:] == кор:
            return True
    return False


def мусорный(домен):
    """Кандидат, который сайтом предприятия быть не может."""
    d = (домен or '').strip().lower()
    if not d or '.' not in d:
        return 'пустой или не домен'
    if d in ПОЧТОВЫЕ:
        return 'бесплатная почта'
    for п in ПОЧТОВЫЕ:
        if _правка_на_одну(d, п):
            return 'описка почтового домена (%s)' % п
    if ПОРТАЛ.search(d):
        return 'государственный или муниципальный портал'
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import ploshchadki as PL
        if PL.из_списка(d):
            return 'площадка или справочник'
    except Exception:  # noqa: BLE001
        pass
    return ''


def очередь_разбор():
    путь = os.path.join(ZENNO, 'ochered.txt')
    строки = []
    try:
        with open(путь, encoding='utf-8', errors='replace') as f:
            for s in f:
                s = s.strip()
                if s:
                    строки.append(s)
    except OSError:
        pass
    годные, мусор = [], []
    for s in строки:
        ч = s.split(';')
        причина = мусорный(_домен(ч[1] if len(ч) > 1 else ''))
        (мусор if причина else годные).append((s, причина))
    return путь, годные, мусор


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    путь, годные, мусор = очередь_разбор()
    причины = {}
    for _s, п in мусор:
        причины[п] = причины.get(п, 0) + 1
    итог = {'в_очереди': len(годные) + len(мусор), 'мусорных': len(мусор),
            'причины': причины, 'примеры': [s for s, _ in мусор[:10]]}
    if '--ochered' in a and мусор:
        _журнал([{'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'что': 'из очереди',
                  'строка': s, 'почему': п} for s, п in мусор])
        врем = путь + '.new'
        with open(врем, 'w', encoding='utf-8') as f:
            f.write('\n'.join(s for s, _ in годные) + '\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(врем, путь)
        итог['очередь_после'] = len(годные)
    if '--v-hvost' in a:
        # ИЗВЕСТНО ПЛОХИЕ — В КОНЕЦ. Поставив 1 902 кандидата в начало очереди,
        # я обрушил выработку Зенки: она берёт по порядку, а там сайты, которые
        # уже один раз не открылись. Замер: 90 компаний в час против 740–880
        # ночью, и 105 отказов в час. Работу не выбрасываем — переносим в хвост,
        # пусть добираются, когда кончится живое.
        не_откр = set()
        try:
            with open(os.path.join(ZENNO, 'ne_otkrylis.txt'), encoding='utf-8',
                      errors='replace') as f:
                for s in f:
                    s = s.strip()
                    if s:
                        не_откр.add(s.split(';')[0].strip())
        except OSError:
            pass
        живые = [s for s, _ in годные if s.split(';')[0].strip() not in не_откр]
        плохие = [s for s, _ in годные if s.split(';')[0].strip() in не_откр]
        врем = путь + '.new'
        with open(врем, 'w', encoding='utf-8') as f:
            f.write('\n'.join(живые + плохие) + '\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(врем, путь)
        _журнал([{'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'что': 'в хвост',
                  'перенесено': len(плохие), 'осталось_живых_впереди': len(живые)}])
        итог['в_хвост_перенесено'] = len(плохие)
        итог['живых_впереди'] = len(живые)
    if '--kartochki' in a:
        c = sqlite3.connect(ENRICH, timeout=60)
        c.execute('PRAGMA busy_timeout=60000')
        плохие = []
        for i, cs in c.execute("select inn, cand_site from companies "
                               "where coalesce(site,'')='' "
                               "and coalesce(cand_site,'')<>''"):
            п = мусорный(_домен(cs))
            if п:
                плохие.append((str(i), cs, п))
        итог['карточек_с_мусором'] = len(плохие)
        _журнал([{'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'что': 'cand_site',
                  'inn': i, 'было': cs, 'почему': п} for i, cs, п in плохие])
        сделано = 0
        for k in range(0, len(плохие), 200):
            кусок = [(i,) for i, _cs, _п in плохие[k:k + 200]]
            for _ in range(6):
                try:
                    c.executemany("update companies set cand_site='' where inn=?",
                                  кусок)
                    c.commit()
                    сделано += len(кусок)
                    break
                except sqlite3.OperationalError:
                    try:
                        c.rollback()
                    except Exception:  # noqa: BLE001
                        pass
                    time.sleep(5)
        итог['карточек_очищено'] = сделано
        c.close()
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
