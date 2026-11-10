#!/usr/bin/env python3
"""Выжимка из книги по SEO под нашу задачу (доноры, гостевые статьи, GEO, замер).

    python3 kniga_vyzhimka.py <книга.txt> <рабочий каталог>

Текст режется по главам и кускам ~60 тыс. знаков; каждый кусок читает быстрая
модель и выписывает только то, что применимо к нашей задаче, с цитатами. Потом
сильная модель сводит выписки в один отчёт. Каждый ответ пишется на диск сразу
(fsync), готовые куски при перезапуске пропускаются. Текст книги в git не кладём.
"""
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(DIR, '..'))

READER = 'openai:gemini-3.8-flash'
SYNTH = 'claude-opus-5-5'
CHUNK = 60000

ZADACHA = """Наша задача: ООО «Руспром», B2B промышленное оборудование (компрессоры Enger, сайт-каталог
prokompressor.ru, 16 дилерских сайтов; фотосепараторы Meyer). Покупаем гостевые статьи со ссылками на
бирже Miralinks. Проверка прошлой кампании (22 статьи, 37 ссылок) не нашла эффекта: ни роста показов
и позиций, ни переходов, ни заявок. Сейчас перестраиваем отбор доноров: смотрим органику самого места
размещения (Ahrefs), долю проданных статей на площадке, тематику, и делим доноров на SEO (ссылка) и
GEO (упоминание бренда, чтобы ИИ-ассистенты рекомендовали Enger/Meyer). Пишем статьи трёх типов:
нативная без бренда, с одним упоминанием бренда, авторская. Хотим понять, как через 3 месяца надёжно
измерить эффект."""

READ_PROMPT = ZADACHA + """

Ниже фрагмент книги «SEO Монстр 2027» (глава: {glava}). Выпиши ТОЛЬКО то, что применимо к нашей задаче:
- отбор доноров и площадок, признаки плохих и хороших доноров, метрики и пороги;
- гостевые статьи, тексты под ссылку, анкоры, расположение ссылки, число ссылок;
- что сейчас даёт и не даёт ссылочное в Google и Яндексе, санкции, риски;
- упоминания бренда, сущности, GEO, ИИ-ответы, как попасть в рекомендации ИИ;
- альтернативы покупным ссылкам (PR, крауд, digital PR и т.п.), если они сравниваются;
- как измерять эффект ссылок и контента.
Формат: маркированный список, каждый пункт - утверждение автора своими словами + короткая
дословная цитата в кавычках (до 25 слов) + пометка [применимо к: отбор/статьи/GEO/замер/альтернатива].
Не пересказывай общие вещи, которые любой SEO-специалист знает. Ничего не выдумывай: если во
фрагменте нет полезного - ответь одной строкой «НЕТ ПОЛЕЗНОГО».

ФРАГМЕНТ:
{text}"""

SYNTH_PROMPT = ZADACHA + """

Ниже выписки из книги «SEO Монстр 2027» (DrMax), сделанные по кускам. Сведи их в отчёт для владельца:

## 1. Главное для нашей задачи (5-7 пунктов)
## 2. Отбор доноров: что из книги взять в наш план (критерии, пороги, признаки)
## 3. Гостевые статьи и ссылки: что поменять в наших текстах и ссылках
## 4. GEO и упоминания бренда: что книга советует
## 5. Замер эффекта
## 6. Где книга расходится с нашими данными (прошлая кампания не дала эффекта) или с нашим планом
## 7. Что из книги НЕ брать и почему (устаревшее, спорное, не для B2B/РФ)

Каждый пункт - с цитатой из выписок. Ничего не добавляй от себя без пометки «моё мнение».
По-русски, без длинных тире.

ВЫПИСКИ:
{notes}"""


def _call(model, prompt, max_tokens=12000):
    import gen_provider as gp
    from gen_wave import _openai_stream
    if model.startswith('openai:'):
        text, _ = _openai_stream([{'role': 'user', 'content': prompt}], model[7:], max_tokens)
    else:
        msg = gp._raw_stream([{'role': 'user', 'content': prompt}], model, max_tokens,
                             thinking=False, effort=None)
        text = ''.join(b.text for b in msg.content if b.type == 'text')
    return text


def _save(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())


def kuski(text):
    parts = re.split(r'\n(?=### )', text)
    out = []
    for p in parts:
        head = p.split('\n', 1)[0].lstrip('# ').strip()[:80]
        if len(p) < 2000:
            continue
        for i in range(0, len(p), CHUNK):
            out.append((head, p[i:i + CHUNK]))
    return out


def read_one(work, n, glava, text):
    path = os.path.join(work, f'kusok-{n:03d}.md')
    if os.path.exists(path) and os.path.getsize(path) > 10:
        return n, 'уже есть'
    last = None
    for a in range(3):
        if a:
            time.sleep(15 * a)
        try:
            t = _call(READER, READ_PROMPT.format(glava=glava, text=text), 8000)
            if t.strip():
                _save(path, f'<!-- {glava} -->\n' + t.strip())
                return n, 'ок'
            last = 'пусто'
        except Exception as e:
            last = repr(e)[:120]
    return n, 'ОШИБКА ' + str(last)


def main():
    src, work = sys.argv[1], sys.argv[2]
    os.makedirs(work, exist_ok=True)
    text = open(src, encoding='utf-8').read()
    ks = kuski(text)
    print(f'кусков: {len(ks)}', flush=True)
    with ThreadPoolExecutor(6) as ex:
        for n, res in ex.map(lambda a: read_one(work, *a), [(i, g, t) for i, (g, t) in enumerate(ks)]):
            print(f'кусок {n}: {res}', flush=True)
    notes = []
    for i in range(len(ks)):
        p = os.path.join(work, f'kusok-{i:03d}.md')
        if os.path.exists(p):
            s = open(p, encoding='utf-8').read()
            if 'НЕТ ПОЛЕЗНОГО' not in s[:200]:
                notes.append(s)
    print(f'кусков с полезным: {len(notes)}', flush=True)
    out = os.path.join(DIR, 'KNIGA-SEO-MONSTR-2027-VYZHIMKA.md')
    if os.path.exists(out):
        print('сводка уже есть'); return
    t = _call(SYNTH, SYNTH_PROMPT.format(notes='\n\n'.join(notes)), 16000)
    _save(out, '# «SEO Монстр 2027» (DrMax): что полезно для отбора доноров и GEO\n\n'
               f'Выжимка: {len(ks)} кусков прочитаны {READER}, сведены {SYNTH}.\n\n' + t)
    print('сводка ->', out, flush=True)


if __name__ == '__main__':
    main()
