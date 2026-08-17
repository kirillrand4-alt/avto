# -*- coding: utf-8 -*-
"""Семантическая приёмка пробы 12 линзами. Режим ТОЛЬКО ВЕРДИКТЫ: правки не применяются,
чтобы увидеть честные замечания, а не результат автоправки.

Состав линз тот же, что в site-pages/finalize_site.py (страница каталога, не гост-пост):
link и platform берём из SITE_LENSES, 8 общих из finalize_gp.LENSES, плюс 2 инженерные
линзы техпроцесса (teh_technolog, teh_skeptik).
"""
import json, os, sys, re
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'guest-posts'))
sys.path.insert(0, os.path.join(ROOT, 'site-pages'))

import finalize_gp as F
import finalize_site as S

ART = json.load(open(os.path.join(HERE, 'remeza.result.json'), encoding='utf-8'))
BODY = ART['text_html']
PAY = json.load(open(os.path.join(ROOT, 'gen', 'payload-vintovye__elektricheskie_1__remeza.json'),
                     encoding='utf-8'))

# страница каталога prokompressor: link/platform из site-линз, остальные общие
NAMES = ['link', 'platform'] + S.SHARED + ['teh_technolog', 'teh_skeptik']


def head_for(name):
    tpl = S.SITE_LENSES.get(name) or F.LENSES[name]
    if '{links_info}' in tpl:
        tpl = tpl.format(links_info=S.links_of(BODY))
    if '{donor}' in tpl or '{donor_note}' in tpl:
        tpl = tpl.format(donor='prokompressor.ru', donor_note='каталог «Компрессор Центр»')
    return tpl + S.STYLE_ANCHOR


CONTEXT = (
    '\n=== КОНТЕКСТ СТРАНИЦЫ ===\n'
    f'Это нижний текстовый блок страницы каталога prokompressor.ru «{PAY["h1"]}».\n'
    'Тональность нейтральная: бренд страницы не наш, принижать его нельзя, в конце\n'
    'обязателен мост на родной бренд Enger. Подпись автора приклеивается кодом отдельно,\n'
    'в тексте её быть не должно. Правило владельца: любое число в тексте обязано быть\n'
    'в исходных данных страницы, выдуманных цифр быть не может.\n')


def one(name):
    try:
        out, judge = F.call_judge(head_for(name) + F.FMT + CONTEXT +
                                  '\n\n=== СТАТЬЯ ===\n' + BODY)
        passed, edits = F.parse_verdict(out)
        return name, passed, edits, out, judge
    except Exception as e:
        return name, None, [], f'ОШИБКА: {type(e).__name__}: {e}', '-'


def main():
    print(f'линз: {len(NAMES)} -> {", ".join(NAMES)}', flush=True)
    with ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(one, NAMES))
    ok = sum(1 for _, p, _, _, _ in res if p)
    fail = [r for r in res if r[1] is False]
    err = [r for r in res if r[1] is None]
    lines = [f'# Приёмка пробы Remeza: {len(NAMES)} линз, режим только-вердикты\n',
             f'PASS: {ok} | FAIL: {len(fail)} | ошибок: {len(err)}\n']
    for name, passed, edits, out, judge in res:
        mark = 'PASS' if passed else ('FAIL' if passed is False else 'ОШИБКА')
        lines.append(f'\n## {name} - {mark}  (судья: {judge})\n')
        if edits:
            for q, r, why in edits:
                lines.append(f'- «{q[:150]}» -> «{r[:150]}»  _{why}_')
        if passed is not True:
            lines.append('\n<details><summary>сырой вердикт</summary>\n\n```\n'
                         + out[:2600] + '\n```\n</details>')
    open(os.path.join(HERE, 'LENSES-LOG.md'), 'w', encoding='utf-8').write('\n'.join(lines))
    print(f'\nPASS {ok}/{len(NAMES)}, FAIL {len(fail)}, ошибок {len(err)}')
    for name, passed, edits, _, _ in res:
        print(f'  {name:<16} {"PASS" if passed else ("FAIL" if passed is False else "ОШИБКА"):<7} правок: {len(edits)}')
    print('\nлог: probe-remeza/LENSES-LOG.md')


if __name__ == '__main__':
    raise SystemExit(main())
