# -*- coding: utf-8 -*-
r"""Файл 6 Meyer, список (владелец 08.10): из сбора поиском — и основной список КЦ (>= 1,5 млрд), и «ниже
порога»; выручка от 30 млн ИЛИ неизвестна; без напитков. Повторы с файлами Meyer 1–5 не убираются здесь —
помечаются при сборке. Уже собранное по набору poisk (контакты, проверка сайтов моделью, агенты) копируется
в набор meyer6, чтобы не обходить те же сайты второй раз.
"""
import io
import json
import os
import shutil

DIR = r'C:\sender\server'
сп = json.load(io.open(os.path.join(DIR, 'poisk-spisok.json'), encoding='utf-8'))
итог = {}
for раздел in ('компании', 'ниже_порога'):
    for i, к in сп[раздел].items():
        if к['сегм'] == 'напитки' or (к['выручка'] and к['выручка'] < 3e7):
            continue
        итог[i] = dict(к, раздел_кц='основной список КЦ (>= 1,5 млрд)' if раздел == 'компании' else 'ниже порога КЦ')
with io.open(os.path.join(DIR, 'meyer6-spisok.json'), 'w', encoding='utf-8') as f:
    json.dump({'компании': итог, 'снято': {}}, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
сч = {}
for ф_из, ф_в in (('poisk-kontakty.jsonl', 'meyer6-kontakty.jsonl'), ('poisk-sayt-proverka.jsonl', 'meyer6-sayt-proverka.jsonl'),
                  ('poisk-glubokiy.jsonl', 'meyer6-glubokiy.jsonl')):
    if os.path.exists(os.path.join(DIR, ф_в)):
        continue  # уже засеяно (повторный запуск)
    n = 0
    with io.open(os.path.join(DIR, ф_в), 'w', encoding='utf-8') as out:
        for s in io.open(os.path.join(DIR, ф_из), encoding='utf-8', errors='replace'):
            try:
                if json.loads(s).get('inn') in итог:
                    out.write(s if s.endswith('\n') else s + '\n')
                    n += 1
            except ValueError:
                pass
        out.flush()
        os.fsync(out.fileno())
    сч[ф_в] = n
shutil.copyfile(os.path.join(DIR, 'meyer6-spisok.json'), r'C:\seostat\drop\drop-storage\meyer6-spisok.json')
print('готово', json.dumps({'компаний': len(итог), 'основной КЦ': sum(1 for к in итог.values() if к['раздел_кц'].startswith('основной')),
                            'ниже порога': sum(1 for к in итог.values() if к['раздел_кц'].startswith('ниже')),
                            'выручка неизвестна': sum(1 for к in итог.values() if not к['выручка']),
                            'с сайтом': sum(1 for к in итог.values() if к['сайт']), 'засеяно': сч}, ensure_ascii=False), flush=True)
