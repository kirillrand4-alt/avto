# -*- coding: utf-8 -*-
"""Проверка утверждения №1: «страницы руководства дали 188 человек в 69
компаниях, из них 15 главных инженеров».

Считаем по факту в people и сразу гоняем главный тест на дефект дня:
домен source_url ДОЛЖЕН принадлежать той же компании (companies.site по
тому же ИНН). Если человек взят со страницы чужого домена — это ровно тот
случай, когда контакты уехали соседу.

Плюс ищем мусор вместо ФИО.
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

e = EDB.EnrichDB().cx
ИСТ = 'сайт:руководство'


def dom(u):
    u = str(u or '').strip().lower()
    u = re.sub(r'^https?://', '', u)
    u = u.split('/')[0].split('?')[0].split(':')[0]
    if u.startswith('www.'):
        u = u[4:]
    return u


def core(d):
    """Домен без www и без региональных поддоменов первого уровня."""
    p = [x for x in d.split('.') if x]
    return '.'.join(p[-2:]) if len(p) >= 2 else d


def похоже_на_фио(s):
    s = str(s or '').strip()
    if not s:
        return False
    ч = s.split()
    if len(ч) < 2:
        return False
    # каждое слово с заглавной кириллицы, без цифр
    for w in ч:
        if not re.match(r'^[А-ЯЁ][а-яё\-]+\.?$', w):
            return False
    return True


def main():
    print('=== ОБЪЁМЫ ===')
    print('people всего:', e.execute('SELECT COUNT(*) FROM people').fetchone()[0],
          'компаний:',
          e.execute('SELECT COUNT(DISTINCT inn) FROM people').fetchone()[0])
    n, c = e.execute(
        'SELECT COUNT(*), COUNT(DISTINCT inn) FROM people WHERE source=?',
        (ИСТ,)).fetchone()
    ун = e.execute('SELECT COUNT(*) FROM (SELECT DISTINCT inn, person FROM '
                   'people WHERE source=?)', (ИСТ,)).fetchone()[0]
    print('источник %r: строк=%d уник(инн,фио)=%d компаний=%d' % (ИСТ, n, ун, c))
    # сайтовые источники вообще
    like = e.execute(
        "SELECT COUNT(*), COUNT(DISTINCT inn) FROM people WHERE source LIKE "
        "'%сайт%' OR source_url LIKE 'http%'").fetchone()
    print('все «сайтовые»/с url: строк=%d компаний=%d' % like)

    print('=== РОЛИ (источник руководство) ===')
    for r in e.execute('SELECT role, COUNT(*) FROM people WHERE source=? '
                       'GROUP BY role ORDER BY 2 DESC', (ИСТ,)).fetchall()[:25]:
        print('  %-26s %s' % (r[0], r[1]))
    ги = e.execute("SELECT COUNT(*), COUNT(DISTINCT inn) FROM people WHERE "
                   "source=? AND (role LIKE '%гл%инжен%' OR post LIKE "
                   "'%лавный инженер%')", (ИСТ,)).fetchone()
    print('главных инженеров: строк=%d компаний=%d' % ги)

    print('=== ДОМЕН URL vs САЙТ КОМПАНИИ ===')
    rows = e.execute(
        'SELECT p.inn, p.person, p.post, p.role, p.source_url, c.site, c.name '
        'FROM people p LEFT JOIN companies c ON c.inn=p.inn WHERE p.source=?',
        (ИСТ,)).fetchall()
    ок = чужой = нет_сайта = нет_url = 0
    плохие = []
    for inn, per, post, role, url, site, nm in rows:
        if not url:
            нет_url += 1
            continue
        if not site:
            нет_сайта += 1
            continue
        a, b = core(dom(url)), core(dom(site))
        if a == b:
            ок += 1
        else:
            чужой += 1
            плохие.append({'инн': inn, 'фио': per, 'должн': post, 'роль': role,
                           'url_домен': a, 'сайт_компании': b, 'имя': nm,
                           'url': url})
    print('совпал домен=%d ЧУЖОЙ домен=%d без сайта в карточке=%d без url=%d'
          % (ок, чужой, нет_сайта, нет_url))
    for x in плохие[:12]:
        print('  ЧУЖОЙ:', json.dumps(x, ensure_ascii=False)[:300])

    print('=== МУСОР ВМЕСТО ФИО ===')
    мусор = [r for r in rows if not похоже_на_фио(r[1])]
    print('не похоже на ФИО: %d из %d' % (len(мусор), len(rows)))
    for r in мусор[:20]:
        print('  ИНН=%s ФИО=%r должн=%r роль=%r' % (r[0], r[1], r[2], r[3]))

    print('ИТОГ1 строк=%d компаний=%d чужой_домен=%d мусор_фио=%d гл_инж=%d'
          % (n, c, чужой, len(мусор), ги[0]))


if __name__ == '__main__':
    main()
