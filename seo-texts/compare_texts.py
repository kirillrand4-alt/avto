# -*- coding: utf-8 -*-
"""Корпусное сравнение текстов между собой (near-duplicate детект) + повторы FAQ.
Проверяет риск «близкие дубли», отмеченный Яндексом и Гуглом. Без LLM.

Метод: нормализуем текст (снимаем HTML, byline, цифры -> N), берём словесные 5-граммы (шинглы),
считаем Jaccard-похожесть. Для каждой страницы - ближайший сосед; топ самых похожих пар;
отдельно фокус на группах близких фасетов (давление/мощность). FAQ-вопросы - частота повторов.
Выход: similarity-report.md
"""
import json, os, re, glob, itertools
from collections import Counter, defaultdict

DIR = os.path.dirname(os.path.abspath(__file__))


def norm(html):
    h = re.sub(r'<p class="expert-byline">.*?</p>', '', html, flags=re.S)  # убрать авторский блок
    t = re.sub(r'<[^>]+>', ' ', h)
    t = re.sub(r'&nbsp;', ' ', t)
    t = t.lower()
    t = re.sub(r'\d+([.,]\d+)?', 'N', t)          # числа -> N (ловим структурные дубли, не цифры)
    t = re.sub(r'[^а-яёa-z ]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


def shingles(text, k=5):
    w = text.split()
    return set(' '.join(w[i:i + k]) for i in range(max(0, len(w) - k + 1)))


def jac(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def faq_questions(html):
    return [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', q)).strip()
            for q in re.findall(r'accordion-head[^>]*>.*?<span>([^<]+)</span>', html, re.S)]


def main():
    data = {}
    faqs = defaultdict(list)
    cats = {}
    for f in glob.glob(os.path.join(DIR, 'gen', 'result-*.json')):
        s = os.path.basename(f)[len('result-'):-len('.json')]
        pf = os.path.join(DIR, 'gen', f'payload-{s}.json')
        if not os.path.exists(pf):
            continue
        p = json.load(open(pf)); d = json.load(open(f))
        html = d.get('text_html', '')
        data[s] = shingles(norm(html))
        cats[s] = p.get('category', '?')
        for q in faq_questions(html):
            faqs[q.lower()].append(s)
    slugs = list(data)
    n = len(slugs)

    # ближайший сосед для каждой страницы (по всему корпусу) + топ пар
    nn = {}
    pairs = []
    for i in range(n):
        best = 0.0; bj = None
        si = data[slugs[i]]
        for j in range(n):
            if i == j:
                continue
            sim = jac(si, data[slugs[j]])
            if sim > best:
                best = sim; bj = slugs[j]
        nn[slugs[i]] = (best, bj)
    # топ пар (уникальные)
    seen = set()
    for s, (sim, o) in nn.items():
        key = tuple(sorted([s, o])) if o else None
        if key and key not in seen and sim >= 0.4:
            seen.add(key); pairs.append((sim, s, o))
    pairs.sort(reverse=True)

    # распределение похожести ближайшего соседа
    vals = sorted(v[0] for v in nn.values())
    def pct(p): return vals[int(len(vals) * p)] if vals else 0

    lines = ['# Корпусное сравнение текстов (near-duplicate)\n']
    lines.append(f'Страниц: {n}. Метод: 5-граммные шинглы, числа заменены на N (ловим структурные дубли).\n')
    lines.append('## Похожесть на ближайшего соседа (0=уникально, 1=дубль)\n')
    lines.append(f'- медиана: **{pct(0.5):.2f}**')
    lines.append(f'- 75-й перцентиль: {pct(0.75):.2f}')
    lines.append(f'- 90-й перцентиль: {pct(0.90):.2f}')
    lines.append(f'- максимум: {max(vals):.2f}')
    over = {t: sum(1 for v in vals if v >= t) for t in (0.4, 0.5, 0.6, 0.7)}
    lines.append(f'- страниц с ближайшим соседом ≥0.4: {over[0.4]} | ≥0.5: {over[0.5]} | ≥0.6: {over[0.6]} | ≥0.7: {over[0.7]}\n')

    lines.append('## Топ-25 самых похожих пар\n')
    for sim, a, b in pairs[:25]:
        mark = ' ⚠️' if sim >= 0.6 else ''
        lines.append(f'- **{sim:.2f}**{mark} `{a}` ({cats.get(a)}) ↔ `{b}` ({cats.get(b)})')

    # FAQ-повторы
    lines.append('\n## Повторы FAQ-вопросов (один вопрос на многих страницах)\n')
    rep = sorted(((len(v), q) for q, v in faqs.items() if len(v) >= 8), reverse=True)
    lines.append(f'всего уникальных вопросов: {len(faqs)}; повторяющихся (≥8 страниц): {len(rep)}\n')
    for cnt, q in rep[:20]:
        lines.append(f'- {cnt}× — «{q[:80]}»')

    open(os.path.join(DIR, 'similarity-report.md'), 'w', encoding='utf-8').write('\n'.join(lines))
    print(f'готово. страниц {n}. медиана похожести {pct(0.5):.2f}, ≥0.6: {over[0.6]} стр. '
          f'повторяющихся FAQ (≥8): {len(rep)}')


if __name__ == '__main__':
    main()
