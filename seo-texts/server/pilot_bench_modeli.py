# -*- coding: utf-8 -*-
r"""Сравнение моделей шлюза на задачах конвейера Meyer (владелец 09.10: «сделай тесты на нескольких недорогих
моделях, сравни их качество, дай расчёт для всего проекта»).

1. Набор задач (один раз, fsync: pilot-bench-nabor.json) — из данных пилота, ОДИНАКОВЫЙ вход всем моделям:
   T1 роли и ЛПР по подписям (промпт kc_kontakty.ПРОМПТ_НОМЕРА) — 25 компаний, до 8 контактов;
   T2 «чей номер» (kc_audit.ПРОМПТ) — 25 компаний, до 10 номеров без подписи;
   T3 «тот ли сайт» (kc_sayt_proverka.ПРОМПТ) — 30 компаний без ИНН на сайте, текст 3 страниц;
   T4 «подходит под Meyer» (pilot_otbor.ПРОМПТ_БЕЗ_ИНН) — 4 пачки по 25 сайтов без ИНН;
   T5 опровергатель (kc_oproverzhenie.ПРОМПТ) — 15 компаний с ИНН на сайте, улики скрипта.
2. Каждая модель решает весь набор; ответ, токены (usage шлюза) и время — в pilot-bench-otvety.jsonl (резюм).
Разбор и оценка — локально (pilot_bench_analiz.py).
"""
import gzip
import http.client
import io
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
os.environ.setdefault('KC_NABOR', 'pilot')
os.environ.setdefault('POISK_NABOR', 'pilot')
import kc_kontakty as KK  # noqa: E402
import kc_audit as KA  # noqa: E402
import kc_sayt_proverka as KSP  # noqa: E402
import kc_oproverzhenie as KO  # noqa: E402
import pilot_otbor as PB  # noqa: E402
import meyer_nalichie as MN  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'
НАБОР_П = os.path.join(DIR, 'pilot-bench-nabor.json')
ОТВЕТЫ = os.path.join(DIR, 'pilot-bench-otvety.jsonl')
МОДЕЛИ = os.environ.get('BENCH_MODELI', ','.join([
    'claude-opus-5-5', 'claude-fable-5', 'claude-sonnet-4-6', 'claude-sonnet-5-5', 'claude-haiku-4-5',
    'gpt-6-sol', 'gpt-6-luna', 'gpt-5.6-luna', 'deepseek-v4-flash', 'deepseek-v4-pro', 'gemini-3.8-flash',
    'glm-5.3-flash', 'qwen3.8-flash', 'grok-4.7', 'minimax-m3', 'mimo-v2.5-pro', 'kimi-k3'])).split(',')
_лок = threading.Lock()


def jl(п):
    out = {}
    for s in io.open(п, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
            out[з['inn']] = з
        except (ValueError, KeyError):
            pass
    return out


def собрать_набор():
    random.seed(909)
    сп = json.load(io.open(os.path.join(DIR, 'pilot-spisok.json'), encoding='utf-8'))['компании']
    конт = {i: з for i, з in jl(os.path.join(DIR, 'pilot-kontakty.jsonl')).items() if з.get('итог') == 'ok' and i in сп}
    задачи = []
    # T1 роли
    с_подписями = [(i, з) for i, з in конт.items() if sum(1 for н in з.get('номера', []) if н.get('класс')) >= 2]
    for i, з in random.sample(с_подписями, min(25, len(с_подписями))):
        нн = [н for н in з['номера'] if н.get('класс')][:8]
        текст = '\n…\n'.join(н.get('контекст', '') for н in нн)
        задачи.append({'id': 'T1-' + i, 'тип': 'T1', 'вход': KK.ПРОМПТ_НОМЕРА.format(
            домен=MN.домен(з['сайт']), название=сп[i]['имя'], url=нн[0]['страницы'][0], текст=текст[:6500],
            номера='\n'.join('%d. %s' % (j + 1, н.get('номер') or н.get('почта')) for j, н in enumerate(нн)))})
    # T2 чей номер
    без_подписи = [(i, з) for i, з in конт.items() if sum(1 for н in з.get('номера', []) if not н.get('класс') and н.get('номер')) >= 3]
    for i, з in random.sample(без_подписи, min(25, len(без_подписи))):
        нн = [н for н in з['номера'] if not н.get('класс') and н.get('номер')][:10]
        список = '\n'.join('%d. %s — «…%s…»' % (j + 1, н['номер'], (н.get('контекст') or '')[-260:]) for j, н in enumerate(нн))
        задачи.append({'id': 'T2-' + i, 'тип': 'T2', 'вход': KA.ПРОМПТ.format(имя=сп[i]['имя'], инн=i, сайт=з['сайт'], номера=список)})
    # T3 тот ли сайт (ИНН на сайте нет)
    кандидаты = [(i, з) for i, з in конт.items() if i.isdigit() and i not in (з.get('инн_живой') or [])
                 and any(ст == 'ok' for _, ст in з.get('страницы', []))]
    n3 = 0
    for i, з in random.sample(кандидаты, min(60, len(кандидаты))):
        if n3 >= 30:
            break
        тт = KSP.тексты([u for u, ст in з['страницы'] if ст == 'ok'], 3)
        if not тт:
            continue
        к = сп[i]
        задачи.append({'id': 'T3-' + i, 'тип': 'T3', 'вход': KSP.ПРОМПТ.format(
            имя=к['имя'], инн=i, регион=к['регион'], осн=к['осн'], сегм=к['сегм'], выр=round((к['выручка'] or 0) / 1e9, 1),
            сайт=з['сайт'], улики='', текст='\n---\n'.join('[%s] %s' % (u, т) for u, т in тт)[:9000])})
        n3 += 1
    # T4 подходит под Meyer — сайты без ИНН из разбора
    сайты = []
    for s in io.open(os.path.join(DIR, 'pilot-razbor.jsonl'), encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('тип') == 'сайт' and not з.get('инн') and not з.get('унп') and з.get('страниц'):
            qq = [q[2] if isinstance(q, (list, tuple)) else q for q in з.get('запросы', [])]
            сайты.append((з['домен'], з.get('заголовок') or '', з.get('сниппет') or '', (qq or [''])[0]))
    сайты = random.sample(сайты, min(100, len(сайты)))
    сегменты = '; '.join(dict.fromkeys(с.split(' (')[0] for _, с in PB.СЕГМ))
    for k in range(0, len(сайты), 25):
        пачка = сайты[k:k + 25]
        текст = '\n'.join('%d. %s | %s | %s | запрос: %s' % (j + 1, д, з[:120], с[:160], q[:100]) for j, (д, з, с, q) in enumerate(пачка))
        задачи.append({'id': 'T4-%d' % k, 'тип': 'T4', 'домены': [x[0] for x in пачка],
                       'вход': PB.ПРОМПТ_БЕЗ_ИНН.format(сегменты=сегменты, сайты=текст)})
    # T5 опровергатель — ИНН на сайте найден
    с_инн = [(i, з) for i, з in конт.items() if i in (з.get('инн_живой') or [])]
    n5 = 0
    for i, з in random.sample(с_инн, min(30, len(с_инн))):
        if n5 >= 15:
            break
        у, тексты, _, _ = KO.улики(сп[i], з)
        if not тексты:
            continue
        к = сп[i]
        задачи.append({'id': 'T5-' + i, 'тип': 'T5', 'вход': KO.ПРОМПТ.format(
            имя=к['имя'], инн=i, регион=к['регион'], осн=к['осн'], сегм=к['сегм'], выр=round((к.get('выручка') or 0) / 1e6),
            сайт=з['сайт'], улики=у, текст='\n---\n'.join('[%s] %s' % (u, т[:2200]) for u, т in тексты)[:9000])})
        n5 += 1
    with io.open(НАБОР_П, 'w', encoding='utf-8') as f:
        json.dump(задачи, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    return задачи


def дверь(model):
    m = model.lower()
    if m.startswith('claude'):
        return '/v1/messages', True
    return '/v1/chat/completions', False


def вызов(model, prompt):
    """-> (текст, вход_токенов, выход_токенов, секунд). Тот же транспорт, что VC._provider_call_stdlib (gzip+chunked+SSE),
    плюс usage из потока."""
    key = os.environ.get('PROVIDER_API_KEY', '')
    base = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
    put, anth = дверь(model)
    telo = {'model': model, 'max_tokens': 2000, 'stream': True, 'messages': [{'role': 'user', 'content': prompt}]}
    if not anth:
        telo['stream_options'] = {'include_usage': True}
    body = gzip.compress(json.dumps(telo, ensure_ascii=False).encode('utf-8'), 6)
    hdrs = {'content-type': 'application/json', 'accept': 'text/event-stream', 'User-Agent': 'curl/8.5.0',
            'content-encoding': 'gzip'}
    if anth:
        hdrs.update({'x-api-key': key, 'anthropic-version': '2023-06-01'})
    else:
        hdrs['Authorization'] = 'Bearer ' + key

    def gen():
        for i in range(0, len(body), 1200):
            yield body[i:i + 1200]
            time.sleep(0.15)
    t0 = time.time()
    cn = http.client.HTTPSConnection(base.split('//', 1)[-1].split('/')[0], timeout=300)
    try:
        cn.request('POST', put, body=gen(), headers=hdrs)
        rs = cn.getresponse()
        if rs.status != 200:
            raise RuntimeError('HTTP %s: %s' % (rs.status, rs.read(300).decode('utf-8', 'replace')))
        parts, вх, вых = [], 0, 0
        for raw in rs:
            line = raw.decode('utf-8', 'replace').strip()
            if not line.startswith('data:'):
                continue
            h = line[5:].strip()
            if not h or h == '[DONE]':
                continue
            try:
                ev = json.loads(h)
            except ValueError:
                continue
            if ev.get('type') == 'content_block_delta' and (ev.get('delta') or {}).get('type') == 'text_delta':
                parts.append(ev['delta'].get('text', ''))
            elif ev.get('type') == 'message_start':
                u = (ev.get('message') or {}).get('usage') or {}
                вх = u.get('input_tokens', 0) + u.get('cache_read_input_tokens', 0) + u.get('cache_creation_input_tokens', 0)
            elif ev.get('type') == 'message_delta':
                вых = ((ev.get('usage') or {}).get('output_tokens')) or вых
            elif ev.get('type') == 'error':
                raise RuntimeError('stream error: ' + str(ev)[:200])
            if ev.get('choices'):
                for ch in ev['choices']:
                    к = (ch.get('delta') or {}).get('content') or ''
                    if к:
                        parts.append(к)
            if ev.get('usage') and not anth:
                вх = ev['usage'].get('prompt_tokens', вх) or вх
                вых = ev['usage'].get('completion_tokens', вых) or вых
        return ''.join(parts), вх, вых, time.time() - t0
    finally:
        cn.close()


def записать(з):
    with _лок:
        with io.open(ОТВЕТЫ, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def main():
    задачи = json.load(io.open(НАБОР_П, encoding='utf-8')) if os.path.exists(НАБОР_П) else собрать_набор()
    print('задач', len(задачи), {т: sum(1 for з in задачи if з['тип'] == т) for т in ('T1', 'T2', 'T3', 'T4', 'T5')}, flush=True)
    сделано = set()
    if os.path.exists(ОТВЕТЫ):
        for s in io.open(ОТВЕТЫ, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
                if not з.get('ошибка'):
                    сделано.add((з['модель'], з['id']))
            except ValueError:
                pass
    работы = [(м, з) for м in МОДЕЛИ for з in задачи if (м, з['id']) not in сделано]
    print('вызовов', len(работы), flush=True)
    сбои = {}

    def шаг(x):
        м, з = x
        if сбои.get(м, 0) >= 6:  # модель не отвечает — не тратить время
            return
        for попытка in range(2):
            try:
                текст, вх, вых, сек = вызов(м, з['вход'])
                записать({'модель': м, 'id': з['id'], 'тип': з['тип'], 'ответ': текст, 'вх': вх, 'вых': вых,
                          'сек': round(сек, 1), 'вход_символов': len(з['вход'])})
                return
            except Exception as e:  # noqa: BLE001
                ош = str(e)[:200]
                time.sleep(3)
        with _лок:
            сбои[м] = сбои.get(м, 0) + 1
        записать({'модель': м, 'id': з['id'], 'тип': з['тип'], 'ошибка': ош})

    random.shuffle(работы)
    with ThreadPoolExecutor(12) as ex:
        list(ex.map(шаг, работы))
    import shutil
    for п in (НАБОР_П, ОТВЕТЫ):
        shutil.copyfile(п, os.path.join(ДРОП, os.path.basename(п)))
    print('готово', json.dumps(сбои, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
