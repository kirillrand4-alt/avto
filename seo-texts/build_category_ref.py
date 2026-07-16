# -*- coding: utf-8 -*-
"""Досье категорий -> чистые category_reference блоки для payload'ов некомпрессорных страниц.
Снимаем артефакты генерации (<thinking>), внутренние теги [уверенность: …] и строки,
явно помеченные низкой достоверностью. Результат кладём в kb/category-ref/<type>.md и
собираем индекс kb/category-ref/index.json (type -> текст)."""
import os, re, json

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.join(HERE, 'kb')
OUT = os.path.join(KB, 'category-ref')
os.makedirs(OUT, exist_ok=True)

# тип категории -> файл досье
MAP = {
    'ref_dryer':  'category-41-cat.md',            # рефрижераторные осушители
    'ads_dryer':  'category-39-cat.md',            # адсорбционные осушители
    'receiver':   'category-resivery.md',          # ресиверы
    'filter':     'category-filtry-magistralnye.md',
    'n2_gen':     'category-generatory-azota.md',
    'o2_gen':     'category-20-cat.md',            # генераторы кислорода
    'separator':  'category-43-cat.md',            # влагомаслоотделители / циклонные сепараторы
    'air_prep':   'category-70-cat.md',            # общий раздел подготовки воздуха
    'spare_parts':'category-53-cat.md',            # запчасти и расходники
    'flowmeter':  'category-37-cat.md',            # расходомеры и датчики
}


def clean(text):
    # убрать <thinking>…</thinking> и любые одиночные теги <…>
    text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.S | re.I)
    text = re.sub(r'</?thinking>', '', text, flags=re.I)
    # выкинуть строки, явно помеченные низкой достоверностью
    kept = []
    for line in text.splitlines():
        low = line.lower()
        if 'уверенность: низк' in low or 'уверенность: low' in low:
            continue
        # снять инлайновый тег достоверности, оставить факт
        line = re.sub(r'\s*\[уверенность:[^\]]*\]', '', line)
        kept.append(line)
    text = '\n'.join(kept)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text


index = {}
for typ, fn in MAP.items():
    p = os.path.join(KB, fn)
    if not os.path.exists(p):
        print('MISSING', fn)
        continue
    raw = open(p, encoding='utf-8').read()
    c = clean(raw)
    op = os.path.join(OUT, f'{typ}.md')
    open(op, 'w', encoding='utf-8').write(c)
    index[typ] = c
    print(f'{typ:12} <- {fn:34} {len(raw)}->{len(c)}ch')

json.dump(index, open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print('\nindex.json:', len(index), 'категорий')
