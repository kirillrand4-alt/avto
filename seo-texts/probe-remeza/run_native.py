# -*- coding: utf-8 -*-
"""Родной контур корпуса 759 (июль), а не августовские линзы гост-постов.

Семь линз, применявшихся к текстам каталога:
  1 филолог          review_philolog.PERSONA
  2 инженер          review_engineer.PERSONA
  3 Яндекс           review_seo.YANDEX
  4 Google           review_seo.GOOGLE
  5 инженер в цикле  regen_driver.ENG_HEAD   (звался на каждой 6-й странице)
  6 инженерный свип  engineer_sweep.HEAD     (флагнул 213 из 759)
  7 SEO «понравится ли ПС»  review_api.PROMPT

ВАЖНО про вызов. Июльские ревьюеры зовут gp.call(...) со штатным thinking, и сегодня
шлюз на этом отдаёт пустой text (content=['thinking','text'], text=''). Поэтому здесь
применён рецепт review_gp.call_robust: сперва _raw_stream(thinking=False), затем
штатный gp.call как запасной путь. Сами промпты июльские, не тронуты.

Гоняем на ДВУХ текстах одной страницы: проба и корпусный, по стандарту, который к
корпусу реально применялся.
"""
import json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import gen_provider as gp
from regen_driver import ENG_HEAD
from review_philolog import PERSONA as PHILOLOG
from review_engineer import PERSONA as ENGINEER
from review_seo import YANDEX, GOOGLE
from engineer_sweep import HEAD as SWEEP_HEAD
from review_api import PROMPT as SEO_API

SLUG = 'vintovye__elektricheskie_1__remeza'
PAY = json.load(open(f'gen/payload-{SLUG}.json', encoding='utf-8'))
MODEL = 'claude-fable-5'

SINGLE_NOTE = ('\n\nВАЖНО: это ОДИН текст, не пачка. Разбери его и дай находки с цитатами '
               '(или «чисто»). В конце - короткий вывод: что опасно/вредно, что полезно, '
               'чего не хватает.\n\n=== ТЕКСТ ===\n')

LENSES = [
    ('филолог',      PHILOLOG,   SINGLE_NOTE),
    ('инженер',      ENGINEER,   SINGLE_NOTE),
    ('яндекс',       YANDEX,     SINGLE_NOTE),
    ('google',       GOOGLE,     SINGLE_NOTE),
    ('eng_head',     ENG_HEAD,   '\n\n'),
    ('eng_sweep',    SWEEP_HEAD, '\n\n'),
    ('seo_api',      SEO_API,    '\n\n'),
]

VARIANTS = {
    'проба':  json.load(open(f'{HERE}/remeza.result.json', encoding='utf-8')),
    'корпус': json.load(open(f'gen/result-{SLUG}.json', encoding='utf-8')),
}


def plain(d):
    t = re.sub(r'<[^>]+>', ' ', d['text_html']).replace('&nbsp;', ' ')
    return re.sub(r'\s+', ' ', t).strip()


def call_robust(prompt):
    """Рецепт review_gp: thinking=False обходит баг шлюза, затем штатный call."""
    msgs = [{'role': 'user', 'content': prompt}]
    last = None
    for a in range(2):
        if a:
            time.sleep(10)
        try:
            msg = gp._raw_stream(msgs, MODEL, 8000, thinking=False, effort=None)
            text = ''.join(b.text for b in msg.content if b.type == 'text')
            if text.strip():
                return text.strip()
            last = f'пусто, stop={msg.stop_reason}'
        except Exception as e:
            last = repr(e)[:90]
    try:
        msg = gp.call(gp.make_client(), msgs, model=MODEL, attempts=2)
        text = ''.join(b.text for b in msg.content if b.type == 'text')
        if text.strip():
            return text.strip()
    except Exception as e:
        last = repr(e)[:90]
    return f'[ОШИБКА: {last}]'


def job(spec):
    kind, name, persona, note, d = spec
    body = f'### [{PAY.get("category")}] {PAY.get("h1")}\n{plain(d)}\n'
    return kind, name, call_robust(persona + note + body)


def main():
    specs = [(k, n, p, note, d) for k, d in VARIANTS.items() for n, p, note in LENSES]
    print(f'вызовов: {len(specs)} (7 линз x 2 текста)', flush=True)
    with ThreadPoolExecutor(max_workers=5) as ex:
        res = list(ex.map(job, specs))

    lines = ['# Родной июльский контур корпуса 759 на двух текстах одной страницы\n',
             'Семь линз, применявшихся к каталогу. Августовские линзы гост-постов сюда НЕ входят.',
             'Вызов через thinking=False: штатный gp.call сегодня получает от шлюза пустой text.\n']
    for kind in VARIANTS:
        lines.append(f'\n---\n\n# ВАРИАНТ: {kind}\n')
        for k, name, out in res:
            if k == kind:
                lines.append(f'\n## {name}\n\n{out}\n')
    open(f'{HERE}/NATIVE-REVIEW.md', 'w', encoding='utf-8').write('\n'.join(lines))

    print()
    for kind in VARIANTS:
        okn = sum(1 for k, _, o in res if k == kind and not o.startswith('[ОШИБКА'))
        print(f'{kind:<8} получено ответов: {okn}/{len(LENSES)}')
    print('\n=== короткие вердикты (eng_head / eng_sweep) ===')
    for k, name, out in res:
        if name in ('eng_head', 'eng_sweep'):
            print(f'  {k:<8} {name:<10} {out.strip()[:100]}')
    print('\nлог: probe-remeza/NATIVE-REVIEW.md')


if __name__ == '__main__':
    raise SystemExit(main())
