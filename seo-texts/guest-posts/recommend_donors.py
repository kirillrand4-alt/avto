#!/usr/bin/env python3
"""Топ доноров под условия владельца: статьи пишем сами, цена размещения — не по 7000.

Владелец 05.08: «сделай топ из своих рекомендаций под меня, желательно если стоимость
размещения будет не по 7000 каждый, мы же все таки генерируем статьи».

Отсюда логика ранжирования:
  * статьи мы генерируем сами, поэтому платим ТОЛЬКО за размещение — колонка
    «Написание ₽» из июньского медиаплана из расчёта выпадает совсем;
  * качество = балл скоринга × измеренная релевантность (по живым разделам площадки,
    а не по заявленной тематике биржи — она у всей июньской десятки разошлась);
  * цена входит как делитель, а не как фильтр: считаем «качество на 1000 ₽».

Цену НЕ минимизируем вслепую: `DONOR-CRITERIA.md` фиксирует, что за 300-400 ₽ никто
не ведёт редактуру, и hard-фильтр скоринга уже отрезал всё ниже 400 ₽. Поэтому дешёвое
здесь — это «дешевле 7000 при том же качестве», а не «самое дешёвое любой ценой».

    python3 recommend_donors.py [--budget 40000] [--max-price 5000] [-o RECOMMENDED-DONORS.md]
"""
from __future__ import annotations

import argparse
import json
import os

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))

# Ручная разметка поверх автоматики.
#
# Почему она нужна: AUDIENCE-шкала считает улики по словарю, и на DIY-сайтах она даёт
# ложные срабатывания — divankomod.ru (мебель, раздел «мастер-классы») получил 92 балла
# за слова «производство, завод, монтаж, стройка» в статьях про сборку своими руками.
# Отделить промышленного читателя от домашнего мастера по одному словарю нельзя,
# поэтому отраслевые площадки отмечены здесь явно, по названию и структуре разделов.
TIER1 = {
    'russianelectronics.ru': 'журнал «Время электроники»: разделы components, production, market',
    'atomic-energy.ru': 'научно-деловой портал атомной отрасли, трафик 38 тыс.',
    'energoseti.ru': '«Энергетика России»: разделы station, supplier, organization; всего 4 размещения',
    'factories.by': 'справочник производителей: разделы producers, proizvoditeli; 6 размещений',
    'info-svarka.ru': 'сварка и металлообработка: разделы obrabotka-metalla, metally',
}
TIER2 = {
    'vestirama.ru': 'региональное деловое СМИ, есть раздел «Экономика», 10 размещений',
    'sakhapress.ru': 'сетевое издание, трафик 32 тыс. при 4 размещениях — редкая чистота',
    'autopulse05.ru': 'автоблог, трафик 76 тыс. при 0 размещений через биржу; аудитория СТО '
                      'и автосервисов — это наш дилерский слой, но не заводской снабженец',
}
CONSUMER = {
    'divankomod.ru', 'first-apartment.ru', 'f1sh1ng.ru', 'gonimvarim.ru', 'woravel.ru',
    'mirdostupa.ru', 'masternix.ru', 'santehnicheskij-mir.ru', 'obogrev.ru', 'balcony-info.ru',
    'stroyguru.com', 'masteravannoy.ru', 'masterskayapola.ru', 'rosfotooboi.ru',
}

# Доноры, по которым уже есть отдельные основания не брать (аудит страниц, снимок)
FLAGS = {
    'relasko.ru': '448 размещений и раздел размещения — форум, а не редакция',
    'dvobozrenie.ru': 'dofollow лишь в 29% размещений (DONOR-PAGE-AUDIT)',
    'ruscable.ru': '410 размещений — профильный, но конвейер',
    'vpk.name': '471 размещение — профильный, но конвейер',
    'astrakhan.su': '292 размещения',
    'bloknot-volzhsky.ru': '409 размещений',
    'berkat.ru': '273 размещения',
    'russiabase.ru': '248 размещений',
}


def load():
    wb = openpyxl.load_workbook(os.path.join(HERE, 'donors-scored.xlsx'))['Скоринг']
    h = [str(c.value or '') for c in wb[1]]
    S = {n: h.index(n) for n in ['Домен', 'SCORE', 'Трафик', 'ИКС', 'Статей',
                                 'Спам Я %', 'Цена ₽', 'Тематика', '% индекс']}
    score = {}
    for r in wb.iter_rows(min_row=2, values_only=True):
        score[str(r[S['Домен']] or '').lower()] = {k: r[i] for k, i in S.items()}

    p = os.path.join(HERE, 'donor-relevance-all.json')
    if not os.path.exists(p):
        p = os.path.join(HERE, 'donor-relevance.json')
    rel = {r['domain'].lower(): r for r in json.load(open(p, encoding='utf-8'))}
    return score, rel


def build(max_price: float, min_quality: float = 55.0):
    score, rel = load()
    rows = []
    for dom, s in score.items():
        if (s['SCORE'] or 0) < 72:
            continue
        r = rel.get(dom)
        if not r or not r.get('rel_mult'):
            continue                       # не мерено или множитель 0 — не рекомендуем
        price = s['Цена ₽'] or 0
        q = round((s['SCORE'] or 0) * r['rel_mult'], 1)
        if q < min_quality or not price:
            continue
        rows.append({
            'dom': dom, 'quality': q, 'score': s['SCORE'], 'mult': r['rel_mult'],
            'price': price, 'per1000': round(q / price * 1000, 1),
            'razdel': r.get('placement_section'), 'aud': r.get('place_audience'),
            'toks': r.get('toxic_pct'), 'traf': s['Трафик'], 'iks': s['ИКС'],
            'st': s['Статей'], 'spam': s['Спам Я %'], 'tema': str(s['Тематика'] or '')[:46],
            'flag': FLAGS.get(dom, ''), 'cheap': price <= max_price, 'tier': tier_of(dom),
        })
    rows.sort(key=lambda x: (-x["quality"], x["price"]))
    return rows


def tier_of(dom: str) -> str:
    if dom in TIER1:
        return '1'
    if dom in TIER2:
        return '2'
    if dom in CONSUMER:
        return 'потреб'
    return '—'


def basket(rows, budget: float, n: int, max_price: float, min_aud: int = 55):
    """Корзина на месяц: лучшие ПО КАЧЕСТВУ в рамках потолка цены и бюджета.

    Ранжировать корзину по «качеству на рубль» нельзя, и это проверено на данных:
    такой порядок собирает дно биржи (401-801 ₽) — самогоноварение, рыбалка, диваны,
    квартиры. Формально у них приличный множитель, фактически ссылка оттуда стоит
    примерно нисколько, потому что промышленного покупателя там нет. Цена входит как
    ПОТОЛОК, а внутри потолка выбор идёт по качеству и по тому, живёт ли на площадке
    наша аудитория (AUDIENCE раздела размещения).
    """
    cand = [r for r in rows
            if r['price'] <= max_price and not r['flag']
            and r['dom'] not in CONSUMER
            and (r['dom'] in TIER1 or r['dom'] in TIER2 or (r['aud'] or 0) >= min_aud)]
    # отраслевые (TIER1) идут первыми при прочих равных: там статья - родной контент
    cand.sort(key=lambda x: (0 if x['dom'] in TIER1 else 1 if x['dom'] in TIER2 else 2,
                             -x['quality'], x['price']))
    out, spent = [], 0
    for r in cand:
        if len(out) >= n:
            break
        if spent + r['price'] > budget:
            continue
        out.append(r)
        spent += r['price']
    return out, spent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--budget', type=float, default=40000)
    ap.add_argument('--max-price', type=float, default=5000)
    ap.add_argument('--count', type=int, default=10)
    ap.add_argument('--min-aud', type=int, default=55, dest='min_aud')
    ap.add_argument('-o', '--out', default='RECOMMENDED-DONORS.md')
    args = ap.parse_args()

    rows = build(args.max_price)
    bask, spent = basket(rows, args.budget, args.count, args.max_price, args.min_aud)

    L = []
    a = L.append
    a('# Рекомендованный топ доноров (статьи пишем сами)')
    a('')
    a('Условие владельца 05.08: «сделай топ из своих рекомендаций под меня, желательно')
    a('если стоимость размещения будет не по 7000 каждый, мы же все таки генерируем статьи».')
    a('')
    a('Раз статьи генерируем сами, платим только за размещение — колонка «Написание ₽» из')
    a('июньского медиаплана из расчёта убрана.')
    a('')
    a('**Как считалась корзина и почему не «эффект на рубль».** Первый вариант ранжировал')
    a('по «качество / цена» — и собрал дно биржи: самогоноварение, рыбалка, диваны, квартиры')
    a('по 401-801 ₽. Формально множитель релевантности у них приличный, фактически ссылка')
    a('оттуда стоит примерно нисколько: промышленного покупателя там нет. Поэтому цена')
    a('входит как ПОТОЛОК, а внутри потолка выбор идёт по качеству и по отраслевому слою.')
    a('')
    a('**Известная слабость автоматики.** AUDIENCE-шкала считает улики по словарю и на DIY-')
    a('сайтах ошибается: divankomod.ru (мебель, раздел «мастер-классы») получил 92 балла за')
    a('слова «производство, завод, монтаж, стройка» в статьях про сборку своими руками.')
    a('Отделить снабженца от домашнего мастера одним словарём нельзя, поэтому отраслевые')
    a('площадки размечены руками по названию и структуре разделов — колонка «слой».')
    a('')
    a(f'## Корзина на месяц: {len(bask)} размещений, {spent:.0f} ₽')
    a('')
    a(f'Потолок цены {args.max_price:.0f} ₽ за размещение, бюджет {args.budget:.0f} ₽.')
    a('Доноры с отдельными основаниями против (конвейер, слабый dofollow) в корзину')
    a('не берутся — они перечислены ниже отдельно.')
    a('')
    a('| # | Донор | Цена | Слой | Качество | Раздел | Трафик | Размещений | Почему в списке |')
    a('|---|---|---|---|---|---|---|---|---|')
    for i, r in enumerate(bask, 1):
        why = TIER1.get(r['dom']) or TIER2.get(r['dom']) or r['tema']
        a(f"| {i} | {r['dom']} | **{r['price']:.0f} ₽** | {r['tier']} | {r['quality']} | "
          f"{r['razdel']} | {r['traf']} | {r['st']} | {why} |")
    a('')
    if bask:
        a(f"Средний чек размещения — **{spent / len(bask):.0f} ₽**. Для сравнения: в июньском")
        a('медиаплане размещение + написание давали 462-4950 ₽ за донора, причём написание')
        a('составляло от 100 до 520 ₽ — то есть основная экономия здесь не на текстах,')
        a('а на выборе площадок.')
        a('')

    a('## Полный ранжир по качеству')
    a('')
    a('| Донор | Цена | Слой | Качество | Балл | ×релев. | Раздел | AUD | Размещений | Оговорка |')
    a('|---|---|---|---|---|---|---|---|---|---|')
    for r in rows[:30]:
        mark = '' if r['cheap'] else ' ⚠️выше потолка'
        a(f"| {r['dom']} | {r['price']:.0f} ₽{mark} | {r['tier']} | {r['quality']} | {r['score']} | "
          f"{r['mult']} | {r['razdel']} | {r['aud']} | {r['st']} | {r['flag'] or '—'} |")
    a('')

    flagged = [r for r in rows[:40] if r['flag']]
    if flagged:
        a('## Хорошие по цифрам, но с оговоркой')
        a('')
        for r in flagged:
            a(f"- **{r['dom']}** ({r['price']:.0f} ₽, качество {r['quality']}) — {r['flag']}.")
        a('')

    a('## Как это считалось')
    a('')
    a('1. Корзина A свежего скоринга (SCORE ≥ 72) — 191 донор.')
    a('2. По каждому измерена релевантность краулом живых разделов (`donor_relevance.py`):')
    a('   AUDIENCE-шкала «где живёт наш покупатель», гейт по токсичности (порог 1%),')
    a('   штраф доскам объявлений. Множитель 0 = отказ, такие сюда не попадают.')
    a('3. Качество = SCORE × множитель. Эффект = качество / цена × 1000.')
    a('4. Из корзины исключены доноры с отдельными основаниями против.')
    a('')
    a('Чего в расчёте НЕТ и что стоит добавить перед закупкой: доля проиндексированных')
    a('размещений и доля dofollow по конкретному донору. Это меряется `audit_donor_pages.py`')
    a('и выгрузкой Ahrefs (UR по страницам-источникам) — именно этот шаг снял в своё время')
    a('dvobozrenie.ru, который по цифрам выглядел отлично.')

    open(os.path.join(HERE, args.out), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print(f'кандидатов с измеренной релевантностью и качеством >= 55: {len(rows)}')
    print(f'корзина: {len(bask)} размещений на {spent:.0f} ₽ '
          f'(средний чек {spent / max(1, len(bask)):.0f} ₽)')
    print()
    for i, r in enumerate(bask, 1):
        print(f"{i:>2}. {r['dom']:<26}{r['price']:>7.0f} ₽  качество {r['quality']:>5}  "
              f"на 1000 ₽ {r['per1000']:>5}  {r['razdel']}")
    print(f'\n-> {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
