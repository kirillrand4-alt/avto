#!/usr/bin/env python3
"""Упаковка готовых статей в формат загрузки Miralinks.

Владелец 06.08 прислал шаблон биржи (miralinks_article_sample.zip): плоский архив из
файлов `art_N.txt`, внутри блоки `[__ключ__]` со значением на следующих строках.
Формат воспроизводится побайтно: UTF-8 без BOM, переводы строк CRLF, пустая строка
между блоками, финальный CRLF.

    python3 make_miralinks_zip.py [-o ARTICLES-MIRALINKS.zip]

Ключевые поля и откуда берутся:
  title            - заголовок статьи (meta.title, он же H1)
  description      - краткое описание для биржи (meta.description)
  metatitle        - тег Title страницы
  metakeywords     - ключи из seo-поля джобы генератора
  metadescription  - тег Description
  slug             - рекомендуемое имя для URL
  snippet          - анонс (meta.anons)
  content          - тело статьи в HTML
  ground           - площадка, к которой привязывается статья (донор из журнала)

Поля video_* остаются пустыми: видео мы не размещаем, но блоки сохраняем -
шаблон биржи их содержит, и убирать их из структуры рискованно.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))

FIELDS = ['title', 'description', 'metatitle', 'metakeywords', 'metadescription',
          'slug', 'snippet', 'content', 'ground', 'video_links', 'video_requirements']

STOP = set('и в во не на с со а то что как для от до по из у о при над под без же бы ли '
           'это этот эта эти или если так там где чем чем-то тоже также его её их'.split())


def keywords(job_seo: str, title: str, html: str, limit: int = 9) -> str:
    """Ключи для metakeywords: сначала из seo-поля джобы, добор - по тексту."""
    keys = []
    for m in re.finditer(r'«([^»]{4,60})»', job_seo or ''):
        k = m.group(1).strip().lower()
        if k not in keys:
            keys.append(k)
    if len(keys) < limit:
        text = re.sub(r'<[^>]+>', ' ', html).lower()
        freq: dict = {}
        for w in re.findall(r'[а-яё]{5,}', text):
            if w not in STOP:
                freq[w] = freq.get(w, 0) + 1
        for w, _ in sorted(freq.items(), key=lambda x: -x[1]):
            if len(keys) >= limit:
                break
            if not any(w[:6] in k for k in keys):
                keys.append(w)
    return ', '.join(keys[:limit])


SNIPPET_MAX = 255       # ограничение биржи: «Текст анонса: не более 255 символов»

# служебные слова, на которых нельзя обрывать анонс
TAIL_STOP = set('и а но или для от до по из у о об в во на с со за над под при без же бы ли '
                'что как чтобы если когда где чем то это тот та те к ко их его её не ни '
                'также тоже потому поэтому однако между через около после перед'.split())


def snippet(meta: dict, html: str) -> str:
    """Анонс под лимит биржи.

    Первая загрузка отвалилась на 9 статьях из 15 именно здесь: анонсы генератора
    выходили на 282-411 знаков. Ещё у пяти статей анонса не было вовсе - они
    загрузились с пустым полем, что тоже плохо. Поэтому: берём анонс, если он есть,
    иначе description, иначе первый абзац; режем по границе предложения, а если
    предложение одно и длинное - по границе слова, без обрыва на полуслове.
    """
    text = (meta.get('anons') or '').strip()
    if not text:
        text = (meta.get('description') or '').strip()
    if not text:
        m = re.search(r'(?s)<p>(.*?)</p>', html)
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', m.group(1))).strip() if m else ''
    text = re.sub(r'\s+', ' ', text)
    if len(text) <= SNIPPET_MAX:
        return text

    # Режем по границе предложения. Если первое предложение само длиннее лимита -
    # по границе слова, но тогда обязательно снимаем хвостовые служебные слова:
    # без этого получалось «критерии подбора оборудования для.» - обрыв на предлоге
    # с точкой, который читается как брак.
    cut = text[:SNIPPET_MAX]
    end = max(cut.rfind('. '), cut.rfind('! '), cut.rfind('? '))
    if end >= 120:
        return cut[:end + 1].strip()

    words = cut[:cut.rfind(' ')].split()
    while words and words[-1].lower().strip('.,;:—-') in TAIL_STOP:
        words.pop()
    return ' '.join(words).rstrip(' ,;:-—') + '…'


def body_html(path: str) -> str:
    """Тело статьи. H1 биржа ставит из title, поэтому из content его убираем."""
    s = open(path, encoding='utf-8').read()
    s = re.sub(r'(?s)^\s*<h1>.*?</h1>\s*', '', s)
    return s.strip()


def block(name: str, value: str) -> str:
    return f'[__{name}__]\r\n' + (value or '').replace('\n', '\r\n') + '\r\n'


def load_jobs() -> dict:
    """seo-поля из всех волн генератора - нужны для metakeywords."""
    import sys
    sys.path.insert(0, HERE)
    jobs = {}
    for mod in ('gen_wave', 'gen_wave2', 'gen_wave3'):
        try:
            m = __import__(mod)
            for j in getattr(m, 'JOBS', []):
                jobs[j['slug']] = j
        except Exception:                                    # noqa: BLE001
            pass
    return jobs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('-o', '--out', default='ARTICLES-MIRALINKS.zip')
    args = ap.parse_args()

    jobs = load_jobs()
    rows = []
    for f in sorted(glob.glob(os.path.join(HERE, 'gp-*.meta.json'))):
        if '.gemini.' in f or '.gpt.' in f:
            continue
        m = json.load(open(f, encoding='utf-8'))
        if not m.get('donor'):          # июльский пилот без донора - площадкам не отдаём
            continue
        html = f.replace('.meta.json', '.html')
        if os.path.exists(html):
            rows.append((m, html))
    rows.sort(key=lambda x: x[0]['donor'])

    out = os.path.join(HERE, args.out)
    idx = ['# Соответствие файлов и статей', '',
           '| Файл | Донор | Статья | Знаков | Анонс |', '|---|---|---|---|---|']
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for i, (m, html_path) in enumerate(rows, 1):
            content = body_html(html_path)
            job = jobs.get(m['slug'], {})
            vals = {
                'title': m.get('title', ''),
                'description': m.get('description', ''),
                'metatitle': m.get('title', ''),
                'metakeywords': keywords(job.get('seo', ''), m.get('title', ''), content),
                'metadescription': m.get('description', ''),
                'slug': m['slug'],
                'snippet': snippet(m, content),
                'content': content,
                'ground': f"https://{m['donor']}/",
                'video_links': '',
                'video_requirements': '',
            }
            assert len(vals['snippet']) <= SNIPPET_MAX, \
                f"{m['slug']}: анонс {len(vals['snippet'])} знаков при лимите {SNIPPET_MAX}"
            body = '\r\n'.join(block(k, vals[k]) for k in FIELDS)
            z.writestr(f'art_{i}.txt', body.encode('utf-8'))
            idx.append(f"| art_{i}.txt | {m['donor']} | {m.get('title','')[:70]} | "
                       f"{m.get('chars')} | {len(vals['snippet'])} |")

    # Указатель кладём РЯДОМ с архивом, а не внутрь: шаблон биржи содержит только
    # art_N.txt, и лишний файл в загрузке может сломать разбор на их стороне.
    open(os.path.join(HERE, 'MIRALINKS-INDEX.md'), 'w', encoding='utf-8').write(
        '\n'.join(idx) + '\n')

    print(f'статей: {len(rows)} -> {args.out} ({os.path.getsize(out)} байт)')
    for i, (m, _) in enumerate(rows, 1):
        print(f"  art_{i}.txt  {m['donor']:<24}{m.get('title','')[:64]}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
