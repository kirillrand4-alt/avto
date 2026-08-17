# -*- coding: utf-8 -*-
"""Родной контур корпуса 759 (июль), а не августовские линзы гост-постов.

Состав ровно тот, что применялся к 759:
  * eng_verify / ENG_HEAD из regen_driver - единственная ПОСТРАНИЧНАЯ семантическая
    проверка в конвейере, звалась на каждой 6-й странице;
  * 4 персоны из review_all_50: филолог, инженер, Яндекс, Google.

Гоняем на ДВУХ текстах одной и той же страницы: моя проба и корпусный текст,
чтобы сравнение шло по стандарту, который к корпусу реально применялся.
"""
import json, os, re, sys
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

SLUG = 'vintovye__elektricheskie_1__remeza'
PAY = json.load(open(f'gen/payload-{SLUG}.json', encoding='utf-8'))

SINGLE_NOTE = ('\n\nВАЖНО: это ОДИН текст, не пачка. Разбери его и дай находки с цитатами '
               '(или «чисто»). В конце - короткий вывод: что опасно/вредно, что полезно, '
               'чего не хватает.\n\n=== ТЕКСТ ===\n')

PERSONAS = [('филолог', PHILOLOG), ('инженер', ENGINEER),
            ('яндекс', YANDEX), ('google', GOOGLE)]

VARIANTS = {
    'проба':  json.load(open(f'{HERE}/remeza.result.json', encoding='utf-8')),
    'корпус': json.load(open(f'gen/result-{SLUG}.json', encoding='utf-8')),
}


def plain(d):
    t = re.sub(r'<[^>]+>', ' ', d['text_html']).replace('&nbsp;', ' ')
    return re.sub(r'\s+', ' ', t).strip()


def head(d):
    return f'### [{PAY.get("category")}] {PAY.get("h1")}\n{plain(d)}\n'


def job(spec):
    kind, who, persona, d = spec
    client = gp.make_client()
    try:
        if who == 'ENG_HEAD':
            prompt = ENG_HEAD + f'\n\n[{PAY.get("category")}] {PAY.get("h1")}\n' + plain(d)
            msg = gp.call(client, [{'role': 'user', 'content': prompt}], attempts=2)
        else:
            msg = gp.call(client, [{'role': 'user', 'content': persona + SINGLE_NOTE + head(d)}],
                          model='claude-fable-5', attempts=2)
        out = ''.join(b.text for b in msg.content if b.type == 'text').strip()
    except Exception as e:
        out = f'[ОШИБКА: {e!r}]'
    return kind, who, out


def main():
    specs = []
    for kind, d in VARIANTS.items():
        specs.append((kind, 'ENG_HEAD', None, d))
        for name, p in PERSONAS:
            specs.append((kind, name, p, d))
    print(f'вызовов: {len(specs)}', flush=True)
    with ThreadPoolExecutor(max_workers=5) as ex:
        res = list(ex.map(job, specs))

    lines = ['# Родной контур корпуса 759 на двух текстах одной страницы\n',
             'Контур июльский: ENG_HEAD (постранично, каждая 6-я) + 4 персоны review_all_50.',
             'Августовские линзы гост-постов сюда НЕ входят.\n']
    for kind in VARIANTS:
        lines.append(f'\n---\n\n# ВАРИАНТ: {kind}\n')
        for k, who, out in res:
            if k != kind:
                continue
            lines.append(f'\n## {who}\n\n{out}\n')
    open(f'{HERE}/NATIVE-REVIEW.md', 'w', encoding='utf-8').write('\n'.join(lines))

    print('\n=== ENG_HEAD (однострочный вердикт) ===')
    for k, who, out in res:
        if who == 'ENG_HEAD':
            print(f'  {k:<8} {out.strip()[:110]}')
    print('\nлог: probe-remeza/NATIVE-REVIEW.md')


if __name__ == '__main__':
    raise SystemExit(main())
