# -*- coding: utf-8 -*-
"""Провайдерская документация всех модулей sender (claude-fable-5, параллельно).
На каждый модуль: назначение, ИСТОЧНИКИ данных (файлы/БД/API/env), логика
обработки, где трогает БД (SQLite store), внешние зависимости, ПЕРЕСЕЧЕНИЯ с
другими модулями. Итог — module-docs.json для сборки SENDER-ARCHITECTURE.md."""
import os, sys, json, glob, re
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')
import gen_provider

DIR = os.path.dirname(os.path.abspath(__file__))
MODS = sorted(f for f in glob.glob(os.path.join(DIR, '*.py'))
              if not os.path.basename(f).startswith(('test_', 'gen_module_docs', '__')))
NAMES = [os.path.basename(m)[:-3] for m in MODS]
NAMES_STR = ', '.join(NAMES)

PROMPT = """Ты — архитектор, документирующий модуль Python-системы холодной email-рассылки
(self-hosted аналог coldy.ai). Проанализируй ИСХОДНИК модуля `{name}` и верни строгий
JSON. Пиши по-русски, конкретно, по коду (не выдумывай).

Все модули системы: {names}.

Верни СТРОГО JSON без markdown:
{{
 "module": "{name}",
 "one_line": "одна строка: зачем модуль",
 "responsibilities": ["ключевые обязанности, по коду"],
 "data_sources": ["ОТКУДА берёт данные: конкретные файлы, таблицы БД, HTTP/IMAP/SMTP API, env-переменные, конфиг-ключи"],
 "processing_logic": ["как обрабатывает: основные шаги/алгоритмы/правила по коду"],
 "db_touchpoints": ["какие таблицы/операции store.py (SQLite) читает/пишет; пусто если БД не трогает"],
 "external_io": ["сеть/файлы/процессы наружу: SMTP, IMAP, HTTP-эндпоинты, провайдерский API, файлы"],
 "public_api": ["ключевые публичные функции/классы, которые вызывают другие модули"],
 "depends_on": ["какие ДРУГИЕ модули системы импортирует/использует"],
 "overlaps": ["с какими модулями логика ПЕРЕСЕКАЕТСЯ или дублируется и в чём именно; пусто если нет"]
}}

ИСХОДНИК {name}.py:
```python
{src}
```"""

def doc_one(path):
    name = os.path.basename(path)[:-3]
    src = open(path, encoding='utf-8').read()
    if len(src) > 48000:
        src = src[:48000] + '\n# ...(обрезано)...'
    prompt = PROMPT.format(name=name, names=NAMES_STR, src=src)
    for a in range(5):
        try:
            msg = gen_provider._raw_stream([{'role': 'user', 'content': prompt}],
                                           'claude-fable-5', 2500, thinking=False)
            t = ''.join(b.text for b in msg.content if getattr(b, 'type', '') == 'text')
            blob = _find_json(t)
            d = json.loads(blob)
            d['module'] = name
            d['_lines'] = src.count('\n')
            return d
        except Exception as ex:
            if a == 4:
                return {'module': name, 'error': str(ex)[:120], '_lines': src.count('\n')}

def _find_json(raw):
    s = depth = 0; s = -1; instr = esc = False
    for i, ch in enumerate(raw):
        if s == -1:
            if ch == '{': s, depth = i, 1
            continue
        if instr:
            if esc: esc = False
            elif ch == '\\': esc = True
            elif ch == '"': instr = False
            continue
        if ch == '"': instr = True
        elif ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0: return raw[s:i + 1]
    return None

if __name__ == '__main__':
    print(f'модулей к документированию: {len(MODS)}', file=sys.stderr, flush=True)
    with ThreadPoolExecutor(max_workers=10) as ex:
        docs = list(ex.map(doc_one, MODS))
    docs.sort(key=lambda d: d['module'])
    json.dump(docs, open(os.path.join(DIR, 'module-docs.json'), 'w'),
              ensure_ascii=False, indent=1)
    ok = sum(1 for d in docs if 'error' not in d)
    print(f'готово: {ok}/{len(docs)} модулей', file=sys.stderr)
    for d in docs:
        if 'error' in d:
            print(f"  ОШИБКА {d['module']}: {d['error']}", file=sys.stderr)
