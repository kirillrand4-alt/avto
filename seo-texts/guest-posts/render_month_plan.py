#!/usr/bin/env python3
"""Сборка MONTH-PLAN.md из трёх источников: солвер + съём с сервера + линзы.

    python3 render_month_plan.py
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'MONTH-PLAN.md')

SITE = {'enger': 'Enger', 'prokom': 'ProKompressor'}


def load(name):
    p = os.path.join(HERE, name)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else None


def main() -> int:
    plan = load('month-plan.json')
    eyes = load('donor-eyes-raw.json') or {}
    lens = {x['donor']: x for x in (load('plan-lenses.json') or [])}

    L = []
    a = L.append
    a('# Месячная раскладка размещений (доноры 1-10 приоритета владельца)')
    a('')
    a('Задача владельца 05.08.2026: доноры 1-10 из `donors-prioritized.xlsx`, размещение')
    a('за один месяц, 1-3 ссылки в статье, доля Enger:ProKompressor = 40:60 в пользу')
    a('ProKompressor, каждый дилерский домен использован минимум один раз.')
    a('')
    a('Раскладку считает `plan_month.py` (перебор под жёсткие ограничения + независимая')
    a('валидация), доноров проверяет `donor_eyes.py` (браузер с сервера владельца,')
    a('дельфин-профили с мобильными прокси), подтверждают `plan_lenses.py` (три линзы')
    a('на разных моделях + судья).')
    a('')

    a('## Сводка')
    a('')
    a(f"| Показатель | Значение |")
    a('|---|---|')
    a(f"| Статей за месяц | {len(plan['rows'])} (по одной на донора) |")
    a(f"| Ссылок всего | {plan['links_total']} |")
    a(f"| На ядро (Enger + ProKompressor) | {plan['core_total']} |")
    a(f"| Enger / ProKompressor | {plan['enger']} / {plan['prokom']} = **{plan['ratio']}** |")
    a(f"| Дилерских ссылок | {plan['links_total'] - plan['core_total']} "
      f"(покрыты все {len(plan['dealers_covered'])}) |")
    a(f"| Проверка ограничений | {'нарушений нет' if not plan['validation'] else '; '.join(plan['validation'])} |")
    a('')

    a('## ⚠️ Заявленной тематике доноров верить нельзя (съём с сервера)')
    a('')
    a('Требование владельца: «тематике особо не верь у доноров, лучше перепроверь глазами')
    a('с сервера». Проверили — колонка тематики в выгрузке биржи проставлена вебмастером')
    a('и не верифицируется. Ниже — что площадка заявляет и что на ней реально.')
    a('')
    a('| # | Донор | Заявлено биржей | Разделы сайта по факту | Вывод линзы |')
    a('|---|---|---|---|---|')
    for r in sorted(plan['rows'], key=lambda x: x['prio']):
        dom = r['donor']
        e = eyes.get(dom, {})
        nav = ', '.join(x['text'] for x in e.get('nav', [])[:8]) or '— меню не снято'
        lz = lens.get(dom, {}).get('summary', {})
        verdict = lz.get('совпадение', '—')
        fact = lz.get('факт_тематика', '—')
        a(f"| {r['prio']} | {dom} | {r['profile']} | {nav} | {verdict}; факт: {fact} |")
    a('')

    a('## Раскладка')
    a('')
    a('| # | Донор | Страницы-акцепторы | Дилер | Ссылок | Место/релев. | Риск | Судья |')
    a('|---|---|---|---|---|---|---|---|')
    for r in sorted(plan['rows'], key=lambda x: x['prio']):
        core = '<br>'.join(
            f"№{c['n']} [{SITE[c['site']]}] {c['segment']}"
            + ('' if c['from_matrix'] else ' ⚠️вне матрицы')
            for c in r['core'])
        deal = ', '.join(x['key'] for x in r['dealers']) or '—'
        lz = lens.get(r['donor'], {}).get('summary', {})
        ready = ' *(статья готова)*' if r['ready'] else ''
        a(f"| {r['prio']} | {r['donor']}{ready} | {core} | {deal} | {r['links']} | "
          f"{lz.get('место', '—')}/{lz.get('релевантность', '—')} | {lz.get('риск', '—')} | "
          f"{lz.get('итог', '—')} |")
    a('')

    a('### Расход квоты акцепторов')
    a('')
    a('| № | Страница | Было ссылок | В этом месяце | Квота | Остаток |')
    a('|---|---|---|---|---|---|')
    seg = {c['n']: (c['segment'], c['site']) for r in plan['rows'] for c in r['core']}
    for n, u in sorted(plan['acceptor_usage'].items(), key=lambda x: int(x[0])):
        month = u['used_month'] - sum(1 for r in plan['rows'] if r['ready']
                                      for c in r['core'] if c['n'] == int(n))
        total = u['prior'] + month
        if not (month or u['prior']):
            continue
        s = seg.get(int(n), ('—', ''))
        a(f"| {n} | {s[0]} {('[' + SITE.get(s[1], '') + ']') if s[1] else ''} | {u['prior']} | "
          f"+{month} | {u['quota']} | {u['quota'] - total} |")
    a('')

    a('## Близкие альтернативы (в выбор не попали)')
    a('')
    a('Все проходят те же жёсткие ограничения и уступают победителю только по фит-баллу.')
    a('Малая разница = выбор в этом месте неустойчив, решает линза, а не формула.')
    a('')
    for alt in plan.get('alternatives', []):
        a(f"**A{alt['rank']}** — фит {alt['score']} ({alt['delta']:+}), отличий: {len(alt['diff'])}")
        a('')
        a('| Донор | В плане | В альтернативе |')
        a('|---|---|---|')
        for d in alt['diff']:
            was = ', '.join(f"№{x}" for x in d['was']['core']) + \
                  (' + ' + '/'.join(d['was']['dealers']) if d['was']['dealers'] else '')
            now = ', '.join(f"№{x}" for x in d['alt']['core']) + \
                  (' + ' + '/'.join(d['alt']['dealers']) if d['alt']['dealers'] else '')
            a(f"| {d['donor']} | {was} | {now} |")
        a('')

    if lens:
        a('## Что сказали линзы (подробно)')
        a('')
        for r in sorted(plan['rows'], key=lambda x: x['prio']):
            z = lens.get(r['donor'])
            if not z:
                continue
            s = z['summary']
            a(f"### {r['prio']}. {r['donor']}")
            a('')
            a(f"- **Тематика по факту:** {s['факт_тематика']} (совпадение с заявленным: "
              f"{s['совпадение']}, B2B-слой: {s['b2b_слой']})")
            a(f"- **Размещение:** место {s['место']}, релевантность {s['релевантность']} "
              f"→ {s['вердикт_релевантности']}")
            a(f"- **SEO-риск:** {s['риск']} → {s['решение_риска']}")
            a(f"- **Судья:** {s['итог']} (уверенность {s['уверенность']}) — {s['главное']}")
            a('')

    a('## Порядок работы')
    a('')
    a('1. Записать выбранные пары в `PLACEMENTS-LOG.md` **до** закупки.')
    a('2. Статьи готовить по `PLAYBOOK-GENERATION.md`, тон — `STYLE-GUIDE-GUEST.md`.')
    a('3. Темп: ≤2 новых донорских домена на наш сайт в неделю, ≤1 ссылка на один URL')
    a('   в две недели. Из-за этого №7 и №9 и №10, получающие в месяце по две ссылки,')
    a('   разносятся минимум на две недели.')
    a('4. Публикация на площадке — только после отдельного подтверждения владельца.')
    a('')

    open(OUT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print(f'-> {OUT} ({len(L)} строк)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
