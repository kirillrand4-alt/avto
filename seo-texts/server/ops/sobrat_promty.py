# -*- coding: utf-8 -*-
"""Собрать НАСТОЯЩИЕ промпты панели для десятки и выложить в обменник.

Ничего не генерирует и ничего не пишет в sender.db. Берём ту же десятку, что
и отбор (импортируем pisma_50m), для каждого получателя строим карточку
штатным AiQuota._request и промпт штатным ai_letter.gen_prompt — то есть тот
самый текст, который уходил бы провайдеру. Дальше его отработают агенты.
"""
import inspect
import json
import os
import sys
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\sender')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# pisma_50m читает sys.argv на импорте — подменяем, чтобы он не принял наши
# аргументы за свои; main() при импорте не вызывается.
_argv, sys.argv = sys.argv, ['pisma_50m.py']
import pisma_50m as otbor            # noqa: E402
sys.argv = _argv

from sender import ai_letter          # noqa: E402

SKOLKO = int(sys.argv[1]) if len(sys.argv) > 1 else 10
KAMPANIYA = int(sys.argv[2]) if len(sys.argv) > 2 else 10
IMYA = sys.argv[3] if len(sys.argv) > 3 else 'PROMTY-50M.json'

aq = otbor.aq
vzyato = otbor.tolko_bogatye(KAMPANIYA, SKOLKO)

# Чем панель строит письмо: фиксируем сигнатуры, чтобы вызывать штатно, а не
# на глазок. Если что-то разъедется, это видно в выгрузке.
razvedka = {
    'aq_atributy': [a for a in dir(aq) if not a.startswith('__')][:80],
    'gen_prompt_sig': str(inspect.signature(ai_letter.gen_prompt)),
    'ai_letter_verh': [a for a in dir(ai_letter) if not a.startswith('_')][:60],
}
for imya in ('facts_block', 'judge_prompt', 'vf_prompt', 'teh_lens_prompt', 'gate'):
    f = getattr(ai_letter, imya, None)
    if f:
        razvedka[imya + '_sig'] = str(inspect.signature(f))

# Генератор панели: нужен ради facts (паспорта брендов) — тем же путём, что и
# боевой прогон. Если у AiQuota он уже есть, берём его, а не строим второй.
# Генератор панели нужен РАДИ ФАКТОВ. Правило 5 промпта: «числа только из
# блока ФАКТЫ ниже» — если отдать facts={}, блок уходит пустым (одни прочерки),
# и письмо пишется вообще без разрешённых чисел. Поэтому строим генератор той
# же фабрикой, что и боевой прогон, а не ищем готовый на экземпляре.
gen = None
for kandidat in ('gen', '_gen', 'letter_gen', 'generator'):
    g = getattr(aq, kandidat, None)
    if g is not None and hasattr(g, 'facts'):
        gen, razvedka['gen_otkuda'] = g, 'aq.' + kandidat
        break
if gen is None:
    for fabrika in ('_gen_factory', '_default_gen_factory'):
        f = getattr(aq, fabrika, None)
        if f is None:
            continue
        try:
            gen = f() if callable(f) else None
            if gen is not None:
                razvedka['gen_otkuda'] = fabrika + '()'
                break
        except Exception as e:                 # noqa: BLE001
            razvedka['gen_' + fabrika] = f'{type(e).__name__}: {e}'[:200]
if gen is None:
    razvedka['gen_otkuda'] = 'не найден'

zapisi = []
for i, r in enumerate(vzyato):
    zap = {'nomer': i, 'rid': r.id, 'inn': r.inn, 'email': r.email,
           'company': r.company_name}
    try:
        zapros = aq._request(r)
        zap['request_tip'] = type(zapros).__name__
        zap['request_klyuchi'] = (sorted(zapros.keys())
                                  if isinstance(zapros, dict)
                                  else [a for a in dir(zapros)
                                        if not a.startswith('_')][:60])
        zap['request'] = (zapros if isinstance(zapros, dict)
                          else getattr(zapros, '__dict__', {}) or str(zapros)[:4000])
    except Exception as e:                     # noqa: BLE001
        zap['request_oshibka'] = f'{type(e).__name__}: {e}'[:300]
        zapros = None

    napravlenie = 'kc'
    if isinstance(zap.get('request'), dict):
        napravlenie = (zap['request'].get('division')
                       or zap['request'].get('napravlenie') or 'kc')
    zap['division'] = napravlenie

    if zapros is not None:
        try:
            if gen is not None and hasattr(gen, 'facts_for'):
                fakty = gen.facts_for(napravlenie)
            elif gen is not None and callable(getattr(gen, 'facts', None)):
                fakty = gen.facts()
            elif gen is not None:
                fakty = getattr(gen, 'facts', {}) or {}
            else:
                fakty = {}
        except Exception as e:                 # noqa: BLE001
            fakty, zap['facts_oshibka'] = {}, f'{type(e).__name__}: {e}'[:200]
        # пустой блок фактов = письмо без разрешённых чисел; это надо видеть
        zap['faktov_klyuchey'] = len(fakty) if isinstance(fakty, dict) else -1
        try:
            # angle_base = номер получателя: ротация заходов в партии сквозная
            zap['prompt'] = ai_letter.gen_prompt([zapros], fakty, napravlenie, i)
        except Exception as e:                 # noqa: BLE001
            zap['prompt_oshibka'] = f'{type(e).__name__}: {e}'[:300]
    zapisi.append(zap)


def _bez_nesereal(o):
    try:
        json.dumps(o, ensure_ascii=False)
        return o
    except Exception:                          # noqa: BLE001
        return str(o)[:2000]


vygruzka = {'kampaniya': KAMPANIYA, 'otbor': otbor.otbor_zhurnal,
            'razvedka': razvedka,
            'pisma': json.loads(json.dumps(zapisi, ensure_ascii=False,
                                           default=lambda o: str(o)[:2000]))}
telo = json.dumps(vygruzka, ensure_ascii=False, indent=1).encode()

url, tok = os.environ['DROP_URL'].rstrip('/'), os.environ['DROP_TOKEN']
granica = '----agent' + os.urandom(8).hex()
chasti = (f'--{granica}\r\nContent-Disposition: form-data; name="file"; '
          f'filename="{IMYA}"\r\n\r\n').encode() + telo + f'\r\n--{granica}--\r\n'.encode()
rq = urllib.request.Request(url + '/up', data=chasti, headers={
    'X-Drop-Token': tok,
    'Content-Type': f'multipart/form-data; boundary={granica}'})
with urllib.request.urlopen(rq, timeout=180) as resp:
    otvet = resp.read().decode()[:200]

print(json.dumps({'vzyato': len(vzyato), 'bajt': len(telo), 'fajl': IMYA,
                  'zagruzka': otvet,
                  's_promptom': sum(1 for z in zapisi if z.get('prompt')),
                  'oshibki': [z.get('request_oshibka') or z.get('prompt_oshibka')
                              for z in zapisi if z.get('request_oshibka')
                              or z.get('prompt_oshibka')][:5]},
                 ensure_ascii=False))
