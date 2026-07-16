# -*- coding: utf-8 -*-
"""Post-process: если у страницы есть enger_category_url, а в тексте упомянут Enger БЕЗ ссылки
на его раздел - оборачиваем первое видимое упоминание «Enger»/«Энгер» в ссылку. Детерминированно,
идемпотентно (уже связанные пропускаем). Генерацию не трогает."""
import json, os, re, glob

DIR = os.path.dirname(os.path.abspath(__file__))
# «Enger» (лат., с заглавной) или «Энгер», как отдельное слово, НЕ внутри тега/атрибута/URL
WORD = re.compile(r'(?<![\w">/=-])(Enger|Энгер)(?![\w<"/])')


def fix_one(path):
    slug = os.path.basename(path)[len('result-'):-len('.json')]
    pp = os.path.join(DIR, 'gen', f'payload-{slug}.json')
    if not os.path.exists(pp):
        return False
    payload = json.load(open(pp))
    eu = payload.get('enger_category_url')
    if not eu:
        return False
    d = json.load(open(path))
    h = d.get('text_html', '')
    if not h or eu in h:
        return False  # ссылка на раздел Enger уже стоит
    # оборачиваем ПЕРВОЕ видимое упоминание, которое не внутри уже существующего <a>
    # (грубая защита: не трогаем, если сразу перед совпадением открыт <a ...>)
    m = WORD.search(h)
    if not m:
        return False
    # проверим, что совпадение не внутри тега <...>: считаем незакрытые '<' до позиции
    pre = h[:m.start()]
    if pre.rfind('<') > pre.rfind('>'):
        return False  # внутри тега - не трогаем
    new = h[:m.start()] + f'<a href="{eu}">{m.group(1)}</a>' + h[m.end():]
    d['text_html'] = new
    json.dump(d, open(path, 'w'), ensure_ascii=False, indent=1)
    return True


def main():
    n = 0; fixed = 0
    for f in glob.glob(os.path.join(DIR, 'gen', 'result-*.json')):
        n += 1
        if fix_one(f):
            fixed += 1
    print(f'проверено: {n} | проставлена ссылка Enger: {fixed}')


if __name__ == '__main__':
    main()
