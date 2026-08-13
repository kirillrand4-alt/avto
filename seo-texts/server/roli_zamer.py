# -*- coding: utf-8 -*-
"""Замер: какая модель лучше ставит РОЛИ почтам, при цене рядом с haiku.

Зачем: роли решают, кому уйдёт холодное письмо. Сейчас роли ставит
claude-haiku-4-5 (её задаёт zenno_most.py ключом extract_model). Вопрос
владельца — не найдётся ли за те же деньги модель точнее, и насколько от них
всех отстаёт наш дорогой claude-fable-5.

Честность замера держится на трёх вещах:
  1. ЭТАЛОН СТАВИТ ЧЕЛОВЕК (я), по тем же самым кускам страницы, что уходят
     моделям. Не «правильный ответ по мнению другой модели» — иначе меряем
     похожесть на судью, а не правду.
  2. НИКАКИХ ПОДМЕН МОДЕЛИ. gen_provider.call() при молчании стрима сам
     переводит вызов на запасную модель — для генерации это спасение, для
     замера подлог. Поэтому здесь свой вызов: что попросили, то и спрашиваем,
     а молчание записываем как отказ этой модели.
  3. ЦЕНА ПО ФАКТУ ТОКЕНОВ, из ответа шлюза, а не по прикидке длины.

Файлы (все на сервере, переживают рестарт песочницы):
    roli_etalon_vhod.json    выборка: компания, адрес страницы, текст, адреса
    roli_etalon.json         мой эталон: {инн: {почта: роль}}
    roli_zamer.jsonl         сырые ответы моделей, по строке на (модель, компания)
    roli_zamer_itog.json     сводка

Запуск:
    python roli_zamer.py --progon claude-haiku-4-5
    python roli_zamer.py --vse
    python roli_zamer.py --schet
"""
import json
import os
import re
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
VHOD = os.path.join(DIR, 'roli_etalon_vhod.json')
ETALON = os.path.join(DIR, 'roli_etalon.json')
SYROE = os.path.join(DIR, 'roli_zamer.jsonl')
ITOG = os.path.join(DIR, 'roli_zamer_itog.json')

# Цены шлюза router.cheap, доллары за миллион токенов (вход, выход).
# Со скриншота панели владельца 13.08. Считаем ими, а не догадками.
CENY = {
    'claude-haiku-4-5':  (1.0, 5.0),
    'gpt-5.6-luna':      (0.2, 1.2),
    'gpt-5.4-mini':      (0.75, 4.5),
    'gemini-3.6-flash':  (1.5, 7.5),
    'grok-4.6':          (2.0, 6.0),
    'claude-fable-5':    (10.0, 50.0),
}
MODELI = list(CENY)

# Шкала ролей — копия _ROLE_RANK из enrich_contacts.py. Копия, а не импорт:
# тянуть 670 килобайт модуля ради словаря значит тянуть и его окружение.
RANG = {
    'гл.инженер': 0, 'гл.энергетик': 1, 'гл.механик': 2, 'техдиректор': 3,
    'нач.КС': 4, 'дир.эксплуатации': 5, 'зам.гл.мех/энерг': 6, 'нач.ОГМ': 7,
    'инж.надёжности': 8, 'нач.РМЦ': 9, 'нач.производства': 10, 'гл.технолог': 11,
    'нач.цеха': 12, 'АСУ/КИПиА': 13, 'гл.конструктор': 14, 'техконтакт': 15,
    'охрана труда/ПБ': 15, 'инженер (не главный)': 16,
    'снабжение/закупки': 17, 'директор': 18, 'продажи': 19, 'приёмная': 20,
    'общий': 21, 'бухгалтерия': 22, 'кадры': 23,
}
ROLI_STROKOY = '|'.join(sorted(RANG, key=RANG.get))
# Технические ЛПР — те, ради кого всё и затевалось: по компрессорам решают они.
TEHNICHESKIE = {r for r, v in RANG.items() if v <= 16}


def promt(zapis):
    return (
        'Из куска страницы сайта компании определи РОЛЬ каждого email-адреса.\n'
        'Компания: «%s»%s.\nСтраница: %s\n\n'
        'Роль выбирай СТРОГО из списка (через | ), ничего своего не придумывай:\n%s\n\n'
        'Правила:\n'
        '- роль ставится по тому, что написано РЯДОМ с адресом: должность человека, '
        'название отдела, заголовок блока;\n'
        '- если рядом ничего нет и адрес общий (info@, mail@, office@) — «общий»;\n'
        '- «приёмная» — секретарь и приёмная руководителя, «директор» — сам '
        'руководитель;\n'
        '- «техконтакт» — техническая служба без уточнения должности;\n'
        '- отвечай ТОЛЬКО за адреса из списка ниже, ровно по одной записи на адрес.\n\n'
        'Адреса: %s\n\n'
        'Текст страницы:\n"""\n%s\n"""\n\n'
        'Верни СТРОГО JSON без markdown и без пояснений:\n'
        '{"emails":[{"email":"","role":"","person":"ФИО или пусто"}],'
        '"best_for_outreach":"адрес, которому писать холодное письмо про '
        'компрессорное оборудование (решает технический руководитель, '
        'а не бухгалтерия)"}'
        % (zapis.get('компания') or 'неизвестна',
           (', город ' + zapis['город']) if zapis.get('город') else '',
           zapis.get('url') or '', ROLI_STROKOY,
           ', '.join(zapis['адреса']), zapis.get('текст') or ''))


def _vyzov(model, tekst_promta):
    """Один вызов БЕЗ подмены модели. Возвращает (ответ, usage, ошибка)."""
    import httpx
    baza = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
    klyuch = os.environ.get('PROVIDER_API_KEY', '')
    if not klyuch:
        return '', {}, 'нет PROVIDER_API_KEY'
    # Заголовки как в gen_provider: Cloudflare шлюза отклоняет дефолтные
    # заголовки anthropic-SDK (проверено эмпирически, иначе 403 от WAF).
    headers = {'x-api-key': klyuch, 'anthropic-version': '2023-06-01',
               'content-type': 'application/json', 'accept': 'text/event-stream',
               'User-Agent': 'curl/8.5.0'}
    body = {'model': model, 'max_tokens': 4000, 'stream': True,
            'messages': [{'role': 'user', 'content': tekst_promta}]}
    chasti, usage, nachalo = [], {}, time.time()
    try:
        with httpx.stream('POST', baza + '/v1/messages', headers=headers,
                          json=body, timeout=300.0) as r:
            if r.status_code != 200:
                r.read()
                return '', {}, 'HTTP %d: %s' % (r.status_code, r.text[:180])
            for line in r.iter_lines():
                if time.time() - nachalo > 240:
                    if not chasti:
                        return '', usage, 'молчание стрима 240 с'
                    break
                if not line or not line.startswith('data:'):
                    continue
                p = line[5:].strip()
                if not p or p == '[DONE]':
                    continue
                try:
                    d = json.loads(p)
                except json.JSONDecodeError:
                    continue
                t = d.get('type')
                if t == 'content_block_delta' and (d.get('delta') or {}).get('type') == 'text_delta':
                    chasti.append(d['delta'].get('text', ''))
                elif t == 'message_start':
                    usage.update((d.get('message') or {}).get('usage') or {})
                elif t == 'message_delta':
                    usage.update(d.get('usage') or {})
    except Exception as e:  # noqa: BLE001
        if not chasti:
            return '', usage, '%s: %s' % (type(e).__name__, str(e)[:160])
    return ''.join(chasti), usage, ''


def _json_iz(otvet):
    """Достать JSON из ответа: модели любят обернуть его в markdown или болтовню."""
    s = re.sub(r'^```(?:json)?|```$', '', (otvet or '').strip(),
               flags=re.M).strip()
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


def _sdelano():
    """Что уже прогнано — чтобы повтор не платил дважды и переживал рестарт."""
    bylo = set()
    if os.path.exists(SYROE):
        for s in open(SYROE, encoding='utf-8', errors='replace'):
            try:
                d = json.loads(s)
                bylo.add((d.get('модель'), d.get('инн')))
            except Exception:  # noqa: BLE001
                pass
    return bylo


def progon(model):
    vybor = json.load(open(VHOD, encoding='utf-8'))
    bylo = _sdelano()
    sdelano = propushcheno = 0
    for z in vybor:
        if (model, z['инн']) in bylo:
            propushcheno += 1
            continue
        t0 = time.time()
        otvet, usage, oshibka = _vyzov(model, promt(z))
        zapis = {'модель': model, 'инн': z['инн'], 'секунд': round(time.time() - t0, 1),
                 'usage': usage, 'ошибка': oshibka, 'ответ': _json_iz(otvet),
                 'сырой': (otvet or '')[:400] if not _json_iz(otvet) else ''}
        with open(SYROE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(zapis, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
        sdelano += 1
        print('%s %s %s' % (model, z['инн'], oshibka or 'ok'), flush=True)
    return {'модель': model, 'прогнано': sdelano, 'пропущено_уже_было': propushcheno}


def schet():
    if not os.path.exists(ETALON):
        return {'ошибка': 'нет эталона %s — сначала разметка человеком' % ETALON}
    etalon = json.load(open(ETALON, encoding='utf-8'))
    vybor = {z['инн']: z for z in json.load(open(VHOD, encoding='utf-8'))}
    po_modeli = {}
    for s in open(SYROE, encoding='utf-8', errors='replace'):
        try:
            d = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        m, inn = d.get('модель'), d.get('инн')
        et = (etalon.get(inn) or {}).get('роли') or {}
        if not et:
            continue
        st = po_modeli.setdefault(m, {'адресов': 0, 'точно': 0, 'группа': 0,
                                      'компаний': 0, 'отказов': 0, 'секунд': 0.0,
                                      'вход': 0, 'выход': 0, 'лпр_верно': 0,
                                      'лпр_всего': 0, 'не_ответил_по_адресу': 0})
        st['компаний'] += 1
        st['секунд'] += d.get('секунд') or 0
        u = d.get('usage') or {}
        st['вход'] += int(u.get('input_tokens') or 0)
        st['выход'] += int(u.get('output_tokens') or 0)
        otv = d.get('ответ')
        if not otv:
            st['отказов'] += 1
            st['адресов'] += len(et)
            st['не_ответил_по_адресу'] += len(et)
            continue
        dala = {}
        for e in (otv.get('emails') or []):
            a = str(e.get('email') or '').lower().strip()
            if a:
                dala[a] = str(e.get('role') or '').strip()
        for adres, verno in et.items():
            st['адресов'] += 1
            skazala = dala.get(adres)
            if skazala is None:
                st['не_ответил_по_адресу'] += 1
                continue
            if skazala == verno:
                st['точно'] += 1
            # группа: технический ЛПР или нет — от неё зависит, куда уйдёт письмо
            if (skazala in TEHNICHESKIE) == (verno in TEHNICHESKIE):
                st['группа'] += 1
        lpr_et = (etalon.get(inn) or {}).get('лучший')
        if lpr_et:
            st['лпр_всего'] += 1
            if str(otv.get('best_for_outreach') or '').lower().strip() == lpr_et:
                st['лпр_верно'] += 1

    svod = []
    for m, st in po_modeli.items():
        vh, vy = CENY.get(m, (0, 0))
        cena = st['вход'] / 1e6 * vh + st['выход'] / 1e6 * vy
        n = max(1, st['адресов'])
        svod.append({
            'модель': m,
            'роль_точно_%': round(100 * st['точно'] / n, 1),
            'группа_ЛПР_%': round(100 * st['группа'] / n, 1),
            'выбор_адресата_%': round(100 * st['лпр_верно'] / max(1, st['лпр_всего']), 1),
            'адресов': st['адресов'],
            'пропустила_адресов': st['не_ответил_по_адресу'],
            'отказов_вызова': st['отказов'],
            'сек_на_компанию': round(st['секунд'] / max(1, st['компаний']), 1),
            'токенов_вход': st['вход'], 'токенов_выход': st['выход'],
            '$_за_25_компаний': round(cena, 4),
            '$_за_100k_компаний': round(cena / max(1, st['компаний']) * 100000, 1),
        })
    svod.sort(key=lambda x: (-x['группа_ЛПР_%'], -x['роль_точно_%']))
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
        print(json.dumps(progon(a[1]), ensure_ascii=False, indent=1))
    elif a[0] == '--vse':
        out = []
        for m in MODELI:
            out.append(progon(m))
        print(json.dumps(out, ensure_ascii=False, indent=1))
    elif a[0] == '--schet':
        print(json.dumps(schet(), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
