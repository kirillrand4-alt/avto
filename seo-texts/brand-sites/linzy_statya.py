#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Линзы для готовых СТАТЕЙ, а не для ТЗ.

    python3 linzy_statya.py [--statyi statyi/] [--only inzhener,chitatel]

ЗАЧЕМ ОТДЕЛЬНО ОТ linzy_tz.py. Восемь ролей те же, но предмет другой,
и это не косметика. ТЗ проверяют на то, ПРАВИЛЬНО ЛИ ЗАДАНО; статью -
на то, ЧТО ПОЛУЧИЛОСЬ. Дефекты разные:

  в ТЗ    - неверное правило, выдуманное число, обещание без основания;
  в тексте - скучное вступление, один довод, пересказанный в трёх блоках,
             призыв, который не следует из блока, абзац, который читатель
             пролистает, потому что там нечего узнать.

Ни одна проверка ТЗ такого не видит: там всё это выглядит нормальным
пунктом плана. Механические гейты статей (объём, скелет, тире, воздух/газ,
арифметика) тоже не видят - они про форму и про факты, а не про то,
дочитает ли человек и напишет ли нам.

ЧТО ИДЁТ В ПРОМПТ. Текст статьи и ТЗ, по которому она написана. Без ТЗ
линза не отличит «копирайтер поленился» от «так и было задано», а это
разные дефекты с разной починкой: первый чинится доводкой текста,
второй - правкой генератора ТЗ, то есть сразу на всей сетке.

Результат каждой линзы пишется на диск СРАЗУ с fsync: песочница при
рестарте откатывается (за эту сессию четырежды), накопитель в памяти
пропадает вместе с ней. Повторный запуск готовые линзы пропускает.
"""
import argparse, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(DIR))
sys.path.insert(0, DIR)
import gen_provider as G
from linzy_tz import LINZY as ROLI

# Роли берём из линз ТЗ - они выверены и менять их незачем. Меняем ЗАДАЧУ:
# читать готовый текст глазами этой роли.
HVOST = """

СЕЙЧАС ТЫ ЧИТАЕШЬ НЕ ЗАДАНИЕ, А ГОТОВЫЙ ТЕКСТ СТРАНИЦЫ, написанный
по этому заданию. Задание приложено ниже для сверки.

Отвечай про ТЕКСТ. Замечания к заданию давай только если текст верен,
а виновато задание - это важно различать: текст чинится доводкой одной
страницы, задание чинится в генераторе и сразу на всех двенадцати сайтах.

ЧЕГО НЕ ДЕЛАТЬ:
- не пересказывать текст, автор его знает;
- не предлагать переписать целиком;
- не хвалить. Если место сделано хорошо, скажи одной строкой, чтобы
  его не сломали при правках;
- не выдумывать фактов про рынок и про эти компании.

ФОРМАТ ОТВЕТА - находки по убыванию серьёзности:

## <короткое имя находки>
- где: <цитата из текста, до 15 слов>
- в чём дело: <суть, без воды>
- виновато: текст / задание
- серьёзность: критично / заметно / мелочь

В конце раздел «## Хорошо сделано» - одной строкой на пункт."""


def prompt(rol, statya, tz):
    return f"""{ROLI[rol]}{HVOST}

=== ТЕКСТ СТРАНИЦЫ ===
{statya}
=== КОНЕЦ ТЕКСТА ===

=== ЗАДАНИЕ, ПО КОТОРОМУ ОН НАПИСАН ===
{tz}
=== КОНЕЦ ЗАДАНИЯ ==="""


def _tekst(html):
    h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.S | re.I)
    h = re.sub(r'<h2[^>]*>', '\n\nH2: ', h, flags=re.I)
    h = re.sub(r'</?(p|tr|div|h1|h3)[^>]*>', '\n', h, flags=re.I)
    h = re.sub(r'<[^>]+>', ' ', h)
    return re.sub(r'\n{3,}', '\n\n', re.sub(r'[ \t]+', ' ', h)).strip()


def odna(slug, rol, statya, tz, out_dir, model):
    put = os.path.join(out_dir, f'{slug}.{rol}.md')
    if os.path.exists(put) and os.path.getsize(put) > 400:
        return slug, rol, 'кэш', 0
    t0 = time.time()
    msg = G.call(None, [{'role': 'user', 'content': prompt(rol, statya, tz)}],
                 model=model, attempts=4, max_tokens=20000, thinking_on=False)
    t = ''.join(b.text for b in msg.content if b.type == 'text').strip()
    if len(t) < 200:
        return slug, rol, f'пусто ({len(t)} симв)', time.time() - t0
    os.makedirs(out_dir, exist_ok=True)
    with open(put, 'w', encoding='utf-8') as f:
        f.write(f'# {slug} - линза {rol}\n\n{t}\n')
        f.flush(); os.fsync(f.fileno())
    nahodok = t.count('\n## ') - (1 if 'Хорошо сделано' in t else 0)
    return slug, rol, f'{max(nahodok, 0)} находок', time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--statyi', default=os.path.join(DIR, 'statyi'))
    ap.add_argument('--tz', default=os.path.join(DIR, 'tz'))
    ap.add_argument('--out', default=os.path.join(DIR, 'review-statey'))
    ap.add_argument('--only', help='линзы через запятую')
    ap.add_argument('--stranicy', help='slug через запятую')
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--model', default='claude-fable-5')
    a = ap.parse_args()

    linzy = [x.strip() for x in a.only.split(',')] if a.only else list(ROLI)
    plohie = [x for x in linzy if x not in ROLI]
    if plohie:
        print(f'нет таких линз: {plohie}; есть: {list(ROLI)}', file=sys.stderr)
        return 2

    hochu = {x.strip() for x in a.stranicy.split(',')} if a.stranicy else None
    zadachi = []
    for f in sorted(os.listdir(a.statyi)):
        if not f.endswith('.html'):
            continue
        slug = f[:-5]
        if hochu and slug not in hochu:
            continue
        ptz = os.path.join(a.tz, f'TZ-{slug}.md')
        if not os.path.exists(ptz):
            print(f'  {slug}: нет ТЗ рядом, пропускаю', file=sys.stderr)
            continue
        st = _tekst(open(os.path.join(a.statyi, f), encoding='utf-8').read())
        tz = open(ptz, encoding='utf-8').read()
        for rol in linzy:
            zadachi.append((slug, rol, st, tz))

    print(f'страниц {len(set(z[0] for z in zadachi))}, линз {len(linzy)}, '
          f'вызовов {len(zadachi)}', flush=True)
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(odna, s, r, st, tz, a.out, a.model)
                for s, r, st, tz in zadachi]
        for fu in as_completed(futs):
            try:
                slug, rol, info, sec = fu.result()
                print(f'  {slug} / {rol}: {info} за {sec:.0f} с', flush=True)
            except Exception as e:
                print(f'  СБОЙ: {repr(e)[:160]}', file=sys.stderr, flush=True)
    print(f'\n-> {a.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
