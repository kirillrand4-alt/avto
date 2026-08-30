# -*- coding: utf-8 -*-
"""Механические гейты панели + сборка промптов линз для писем от агентов.

Ничего не пишет в sender.db. Забирает письма из обменника, прогоняет их через
ai_letter.gate / qa_text / brand_facts_lib (это чистый Python, денег не стоит),
и строит ТЕ ЖЕ промпты линз, что уходили провайдеру: teh_lens_prompt('три' —
технолог, скептик, покупатель) и vf_prompt (финальный контролёр). Промпты
отработают агенты.
"""
import json
import os
import sys
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\sender')

from sender import ai_letter          # noqa: E402

ISH = sys.argv[1] if len(sys.argv) > 1 else 'PISMA-AGENTY.json'
KUDA = sys.argv[2] if len(sys.argv) > 2 else 'LINZY-I-GEJTY.json'
PACHKA = 3           # в docstring teh_lens_prompt: партия <=3, иначе обрезает
URL, TOK = os.environ['DROP_URL'].rstrip('/'), os.environ['DROP_TOKEN']


def skachat(imya):
    rq = urllib.request.Request(f'{URL}/{imya}', headers={'X-Drop-Token': TOK})
    with urllib.request.urlopen(rq, timeout=180) as r:
        return json.loads(r.read().decode())


def polozhit(imya, obj):
    telo = json.dumps(obj, ensure_ascii=False, indent=1).encode()
    rq = urllib.request.Request(f'{URL}/{imya}', data=telo, method='PUT',
                                headers={'X-Drop-Token': TOK,
                                         'Content-Type': 'application/json'})
    with urllib.request.urlopen(rq, timeout=180) as r:
        return r.read().decode()[:200]


def poprobovat(modul, imena, argumenty):
    """Вызвать первую подходящую функцию модуля; вернуть (имя, результат)."""
    for imya in imena:
        f = getattr(modul, imya, None)
        if callable(f):
            try:
                return imya, f(*argumenty)
            except TypeError:
                continue
            except Exception as e:                       # noqa: BLE001
                return imya, f'ОШИБКА {type(e).__name__}: {e}'[:300]
    return None, 'подходящей функции нет: ' + ','.join(
        a for a in dir(modul) if not a.startswith('_'))[:300]


d = skachat(ISH)
pisma = d['pisma']

# ---- механические гейты (бесплатные) ----
gejty = []
for z in pisma:
    zapros = z.get('request') or {}
    extra = zapros.get('extra') or {}
    napravlenie = z.get('division') or 'kc'
    rezhim = 'NEWS' if zapros.get('_digest') else 'GENERIC'
    subject, body = z.get('subject') or '', z.get('body') or ''
    itog = {'nomer': z['nomer'], 'rid': z['rid'], 'rezhim': rezhim,
            'company': (zapros.get('company_name') or '')[:40]}
    try:
        itog['gate'] = list(ai_letter.gate(subject, body, mode=rezhim,
                                           extra=extra, facts={},
                                           division=napravlenie) or [])
    except Exception as e:                               # noqa: BLE001
        itog['gate_oshibka'] = f'{type(e).__name__}: {e}'[:300]
    # qa_text лежит НЕ в пакете sender, а в C:\sender\qa_text.py — «from sender
    # import qa_text» даёт ImportError и гейт молча не отрабатывает.
    try:
        import qa_text
        imya, rez = poprobovat(qa_text, ('check', 'naturalness',
                                         'refinement_check'), (body,))
        itog['qa_funkciya'], itog['qa'] = imya, str(rez)[:600]
    except Exception as e:                               # noqa: BLE001
        itog['qa_oshibka'] = f'{type(e).__name__}: {e}'[:300]
    # brand_facts_lib на сервере панели НЕТ ни в C:\sender, ни в пакете sender
    # (в инструкции он назван гейтом достоверности). Фиксируем это как факт, а
    # не делаем вид, что проверка прошла.
    try:
        import brand_facts_lib as bfl
        imya, rez = poprobovat(bfl, ('check_text', 'proverit', 'check',
                                     'validate', 'audit'), (body,))
        itog['brand_funkciya'], itog['brand'] = imya, str(rez)[:500]
    except Exception as e:                               # noqa: BLE001
        itog['brand_oshibka'] = f'{type(e).__name__}: {e}'[:300]
    gejty.append(itog)

# ---- промпты линз (их отработают агенты) ----
promty = []
for nachalo in range(0, len(pisma), PACHKA):
    kusok = pisma[nachalo:nachalo + PACHKA]
    napravlenie = kusok[0].get('division') or 'kc'

    teh_items = []
    for z in kusok:
        zapros = z.get('request') or {}
        # ПАСПОРТ САЙТА ОБЯЗАН ДОЕХАТЬ ДО ЛИНЗЫ. Замер 30.08: у «ЛУЧ» activity
        # пуст, паспорт не передали — линза увидела «профиль неизвестен» плюс
        # ОКВЭД 01.41.21 (молочный скот) и объявила ошибкой упоминание
        # тепловыделяющих элементов. А в блоке получателя генерации сказано
        # прямо: «с их собственного сайта, это ПРОВЕРЕНО». То есть линза
        # забраковала верное письмо ровно по той причине, от которой
        # предостерегает её собственный промпт. Паспорт кладём из карточки
        # генерации (поле pasport), activity — только как запасной.
        teh_items.append((z['nomer'], zapros.get('company_name') or '',
                          zapros.get('activity') or '', zapros.get('okved') or '',
                          z.get('subject') or '', z.get('body') or '',
                          str(z.get('pasport')
                              or zapros.get('extra', {}).get('pasport')
                              or zapros.get('activity') or '')[:1200]))
    vf_items = [(z['nomer'], z.get('subject') or '', z.get('body') or '')
                for z in kusok]
    try:
        promty.append({'vid': 'tri_linzy', 'nomera': [z['nomer'] for z in kusok],
                       'prompt': ai_letter.teh_lens_prompt(teh_items, 'три',
                                                           napravlenie)})
    except Exception as e:                               # noqa: BLE001
        promty.append({'vid': 'tri_linzy', 'oshibka': f'{type(e).__name__}: {e}'[:300]})
    try:
        promty.append({'vid': 'verifikator', 'nomera': [z['nomer'] for z in kusok],
                       'prompt': ai_letter.vf_prompt(vf_items, napravlenie)})
    except Exception as e:                               # noqa: BLE001
        promty.append({'vid': 'verifikator', 'oshibka': f'{type(e).__name__}: {e}'[:300]})

otvet = polozhit(KUDA, {'gejty': gejty, 'promty': promty})
print(json.dumps({
    'pisem': len(pisma), 'promptov': len(promty), 'zagruzka': otvet,
    'chisto_po_gate': sum(1 for g in gejty if not g.get('gate')),
    'gate_kratko': [{'n': g['nomer'], 'narusheniy': len(g.get('gate') or []),
                     'pervye': (g.get('gate') or [])[:2]} for g in gejty],
    'qa_funkciya': gejty[0].get('qa_funkciya') if gejty else None,
    'brand_funkciya': gejty[0].get('brand_funkciya') if gejty else None,
}, ensure_ascii=False, indent=1))
