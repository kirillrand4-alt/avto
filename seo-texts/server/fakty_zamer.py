# -*- coding: utf-8 -*-
"""Замер моделей на СБОРЕ ФАКТОВ. Мерка — проверяемость по тексту, не «похожесть».

Почему нельзя перенести вывод с ролей: там модель размечает короткие куски по
готовой шкале, здесь — вытаскивает продукцию и цифры из 35 тысяч знаков и не
должна ничего досочинить. Дешёвая модель может начать выдумывать правдоподобное,
а это ровно та ошибка, которая убивает письмо.

Поэтому судьёй тут НЕ другая модель и НЕ карточка fable. Судья — сам текст
страницы: каждый пункт продукции и каждая фраза о мощностях проверяются на
вхождение в текст, откуда их взяли.
  * дословно      — строка целиком есть в тексте (нормализованном);
  * по словам     — все значимые слова есть, порядок другой (пересказ, но не выдумка);
  * НЕ НАЙДЕНО    — выдумка либо вывод из ОКВЭД/названия, то есть нарушение ТЗ.
Плюс отдельно: цитата обязана быть дословной, а «мощности» — содержать число.

Запуск:
    python fakty_zamer.py --progon gpt-5.6-luna [сколько]
    python fakty_zamer.py --vse [сколько]
    python fakty_zamer.py --schet
"""
import json
import os
import re
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
sys.path.insert(0, os.path.dirname(DIR))
sys.path.insert(0, r'C:\sender')

SYROE = os.path.join(DIR, 'fakty_zamer.jsonl')
ITOG = os.path.join(DIR, 'fakty_zamer_itog.json')

CENY = {
    'gpt-5.6-luna':      (0.2, 1.2),
    'claude-haiku-4-5':  (1.0, 5.0),
    'gemini-3.6-flash':  (1.5, 7.5),
    'claude-fable-5':    (10.0, 50.0),
}
MODELI = list(CENY)


def _normalizovat(s):
    s = (s or '').lower().replace('ё', 'е')
    s = re.sub(r'[^0-9a-zа-я]+', ' ', s)
    return ' ' + re.sub(r'\s+', ' ', s).strip() + ' '


def _est_doslovno(chto, tekst_n):
    return _normalizovat(chto).strip() in tekst_n


def _est_po_slovam(chto, tekst_n):
    slova = [w for w in _normalizovat(chto).split() if len(w) > 4]
    if not slova:
        return False
    return all((' ' + w) in tekst_n or (w + ' ') in tekst_n for w in slova)


def _proverit(kartochka, tekst_n):
    """Сколько утверждений карточки подтверждается текстом страниц."""
    itog = {'дословно': 0, 'по_словам': 0, 'не_найдено': 0, 'пунктов': 0,
            'мощности_без_числа': 0, 'цитата_дословна': None, 'ne_naydeno_primery': []}
    for pole in ('продукция', 'мощности', 'сырьё', 'контроль_качества',
                 'упаковка_фасовка'):
        for x in (kartochka.get(pole) or []):
            if not isinstance(x, str) or not x.strip():
                continue
            itog['пунктов'] += 1
            if pole == 'мощности' and not re.search(r'\d', x):
                itog['мощности_без_числа'] += 1
            if _est_doslovno(x, tekst_n):
                itog['дословно'] += 1
            elif _est_po_slovam(x, tekst_n):
                itog['по_словам'] += 1
            else:
                itog['не_найдено'] += 1
                if len(itog['ne_naydeno_primery']) < 3:
                    itog['ne_naydeno_primery'].append('%s: %s' % (pole, x[:70]))
    c = kartochka.get('цитата')
    if isinstance(c, str) and c.strip():
        itog['цитата_дословна'] = _est_doslovno(c, tekst_n)
    itog['новостей'] = len([n for n in (kartochka.get('новости') or [])
                            if isinstance(n, dict) and n.get('дата')])
    return itog


def _json_iz(otvet):
    s = re.sub(r'^```(?:json)?|```$', '', (otvet or '').strip(), flags=re.M).strip()
    try:
        return json.loads(s)
    except Exception:  # noqa: BLE001
        pass
    a, b = s.find('{'), s.rfind('}')
    if a >= 0 and b > a:
        try:
            return json.loads(s[a:b + 1])
        except Exception:  # noqa: BLE001
            pass
    return None


def _kompanii(skolko):
    """Компании, у которых есть страницы в кэше: те же входные данные для всех."""
    import site_facts
    import sqlite3
    c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True)
    out = []
    for r in c.execute("select inn, coalesce(name,''), coalesce(site,''), "
                       "coalesce(cand_site,'') from companies "
                       "where inn in (select inn from site_facts "
                       "where coalesce(facts_json,'')<>'')"):
        inn = str(r[0])
        stranicy = site_facts._stranicy(inn)
        if not stranicy:
            continue
        out.append({'inn': inn, 'name': r[1], 'site': r[2] or r[3],
                    'stranicy': stranicy})
        if len(out) >= skolko:
            break
    c.close()
    return out


def _sdelano():
    bylo = set()
    if os.path.exists(SYROE):
        for s in open(SYROE, encoding='utf-8', errors='replace'):
            try:
                d = json.loads(s)
            except Exception:  # noqa: BLE001
                continue
            if d.get('ошибка') or not d.get('карточка'):
                continue
            bylo.add((d.get('модель'), d.get('инн')))
    return bylo


def progon_vseh(modeli, skolko=20, potokov=12):
    """ВСЕ модели и компании РАЗОМ, а не по очереди.

    Владелец 13.08: «ты замеры моделей запускаешь по очереди запросы что ли?».
    Он прав: 80 вызовов подряд по 15-45 секунд — это час на ровном месте, при том
    что вызовы независимы и шлюз держит параллель. Считаем пары «модель+компания»
    и раздаём их пулу. Журнал пишется под замком: строки не должны перемешаться.
    """
    import concurrent.futures as cf
    import threading

    import site_facts
    import gen_provider

    kl = gen_provider.make_client()
    bylo = _sdelano()
    komp = _kompanii(skolko)
    zadaniya = [(m, k) for m in modeli for k in komp if (m, k['inn']) not in bylo]
    zamok = threading.Lock()
    schet_ = {'сделано': 0, 'сбоев': 0}

    def odin(par):
        model, k = par
        tekst = '\n\n'.join('%s\n%s' % (u, t) for u, t in k['stranicy'])
        promt = site_facts.PROMPT % {'name': k['name'], 'inn': k['inn'],
                                     'site': k['site'], 'stranicy': tekst}
        t0 = time.time()
        oshibka, otvet, usage = '', '', {}
        try:
            msg = gen_provider.call(kl, [{'role': 'user', 'content': promt}],
                                    model=model, attempts=2)
            otvet = ''.join(b.text for b in getattr(msg, 'content', [])
                            if getattr(b, 'type', '') == 'text'
                            and getattr(b, 'text', ''))
            u = getattr(msg, 'usage', None)
            usage = {'input_tokens': int(getattr(u, 'input_tokens', 0) or 0),
                     'output_tokens': int(getattr(u, 'output_tokens', 0) or 0)}
        except Exception as e:  # noqa: BLE001
            oshibka = '%s: %s' % (type(e).__name__, str(e)[:180])
        zapis = {'модель': model, 'инн': k['inn'], 'секунд': round(time.time() - t0, 1),
                 'usage': usage, 'ошибка': oshibka, 'карточка': _json_iz(otvet),
                 'знаков_страниц': len(tekst)}
        with zamok:
            with open(SYROE, 'a', encoding='utf-8') as f:
                f.write(json.dumps(zapis, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
            schet_['сделано'] += 1
            if oshibka:
                schet_['сбоев'] += 1
            print('%d/%d %s %s %s' % (schet_['сделано'], len(zadaniya), model,
                                      k['inn'], oshibka or 'ok'), flush=True)

    with cf.ThreadPoolExecutor(max_workers=potokov) as pul:
        list(pul.map(odin, zadaniya))
    return {'заданий': len(zadaniya), 'сбоев': schet_['сбоев'],
            'моделей': len(modeli), 'компаний': len(komp)}


def progon(model, skolko=20):
    import site_facts
    import gen_provider
    kl = gen_provider.make_client()
    bylo = _sdelano()
    sdelano = 0
    for k in _kompanii(skolko):
        if (model, k['inn']) in bylo:
            continue
        tekst = '\n\n'.join('%s\n%s' % (u, t) for u, t in k['stranicy'])
        promt = site_facts.PROMPT % {'name': k['name'], 'inn': k['inn'],
                                     'site': k['site'], 'stranicy': tekst}
        t0 = time.time()
        oshibka, otvet, usage = '', '', {}
        try:
            msg = gen_provider.call(kl, [{'role': 'user', 'content': promt}],
                                    model=model, attempts=2)
            # ТЕКСТ И ТОКЕНЫ БЕРЁМ ПОШТУЧНО. Первый заход писал
            # dict(msg.usage) и dict(...) падал на объекте _Usage —
            # TypeError прилетал ПОСЛЕ удачного вызова, и все 80 ответов
            # (уже оплаченных) ушли в мусор как «отказ».
            otvet = ''.join(b.text for b in getattr(msg, 'content', [])
                            if getattr(b, 'type', '') == 'text'
                            and getattr(b, 'text', ''))
            if not otvet:
                otvet = getattr(msg, 'text', '') or ''
            u = getattr(msg, 'usage', None)
            usage = {'input_tokens': int(getattr(u, 'input_tokens', 0) or 0),
                     'output_tokens': int(getattr(u, 'output_tokens', 0) or 0)}
        except Exception as e:  # noqa: BLE001
            oshibka = '%s: %s' % (type(e).__name__, str(e)[:180])
        kart = _json_iz(otvet)
        zapis = {'модель': model, 'инн': k['inn'], 'секунд': round(time.time() - t0, 1),
                 'usage': usage, 'ошибка': oshibka, 'карточка': kart,
                 'знаков_страниц': len(tekst)}
        with open(SYROE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(zapis, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
        sdelano += 1
        print('%s %s %s' % (model, k['inn'], oshibka or 'ok'), flush=True)
    return {'модель': model, 'прогнано': sdelano}


def schet():
    import site_facts
    # текст страниц для проверки — один раз на компанию
    teksty = {}
    luchshie = {}
    for s in open(SYROE, encoding='utf-8', errors='replace'):
        try:
            d = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        kl = (d.get('модель'), d.get('инн'))
        est = luchshie.get(kl)
        if est is None or (not est.get('карточка') and d.get('карточка')):
            luchshie[kl] = d

    po_modeli = {}
    for (m, inn), d in luchshie.items():
        if inn not in teksty:
            teksty[inn] = _normalizovat(
                '\n'.join(t for _, t in site_facts._stranicy(inn)))
        st = po_modeli.setdefault(m, {'компаний': 0, 'пунктов': 0, 'дословно': 0,
                                      'по_словам': 0, 'не_найдено': 0, 'отказов': 0,
                                      'мощности_без_числа': 0, 'цитат': 0,
                                      'цитат_дословных': 0, 'новостей': 0,
                                      'секунд': 0.0, 'вход': 0, 'выход': 0,
                                      'пусто_продукция': 0, 'примеры_выдумок': []})
        st['компаний'] += 1
        st['секунд'] += d.get('секунд') or 0
        u = d.get('usage') or {}
        st['вход'] += int(u.get('input_tokens') or 0)
        st['выход'] += int(u.get('output_tokens') or 0)
        k = d.get('карточка')
        if not k:
            st['отказов'] += 1
            continue
        if not (k.get('продукция') or []):
            st['пусто_продукция'] += 1
        p = _proverit(k, teksty[inn])
        for pole in ('пунктов', 'дословно', 'по_словам', 'не_найдено',
                     'мощности_без_числа', 'новостей'):
            st[pole] += p[pole]
        if p['цитата_дословна'] is not None:
            st['цитат'] += 1
            st['цитат_дословных'] += int(p['цитата_дословна'])
        for x in p['ne_naydeno_primery']:
            if len(st['примеры_выдумок']) < 5:
                st['примеры_выдумок'].append('%s | %s' % (inn, x))

    svod = []
    for m, st in po_modeli.items():
        n = max(1, st['пунктов'])
        vh, vy = CENY.get(m, (0, 0))
        cena = st['вход'] / 1e6 * vh + st['выход'] / 1e6 * vy
        svod.append({
            'модель': m,
            'подтверждено_дословно_%': round(100 * st['дословно'] / n, 1),
            'подтверждено_с_пересказом_%': round(100 * (st['дословно'] + st['по_словам']) / n, 1),
            'ВЫДУМАНО_%': round(100 * st['не_найдено'] / n, 1),
            'пунктов_на_компанию': round(st['пунктов'] / max(1, st['компаний']), 1),
            'цитата_дословна_%': round(100 * st['цитат_дословных'] / max(1, st['цитат']), 1),
            'мощности_без_числа': st['мощности_без_числа'],
            'новостей_всего': st['новостей'],
            'пусто_продукция': st['пусто_продукция'],
            'компаний': st['компаний'], 'отказов': st['отказов'],
            'сек_на_компанию': round(st['секунд'] / max(1, st['компаний']), 1),
            'токенов_вход': st['вход'], 'токенов_выход': st['выход'],
            '$_за_100k_компаний': round(cena / max(1, st['компаний']) * 100000, 1),
            'примеры_выдумок': st['примеры_выдумок'],
        })
    svod.sort(key=lambda x: (x['ВЫДУМАНО_%'], -x['подтверждено_дословно_%']))
    with open(ITOG, 'w', encoding='utf-8') as f:
        json.dump(svod, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    return svod


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 2
    if a[0] == '--progon':
        print(json.dumps(progon(a[1], int(a[2]) if len(a) > 2 else 20),
                         ensure_ascii=False, indent=1))
    elif a[0] == '--vse':
        n = int(a[1]) if len(a) > 1 else 20
        potokov = int(a[2]) if len(a) > 2 else 12
        print(json.dumps(progon_vseh(MODELI, n, potokov),
                         ensure_ascii=False, indent=1))
    elif a[0] == '--schet':
        print(json.dumps(schet(), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
