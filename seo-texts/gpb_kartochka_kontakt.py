# -*- coding: utf-8 -*-
"""ЭТП ГПБ (etpgpb.ru): контактное лицо заказчика с КАРТОЧКИ закупки.

Списки процедур мы уже умеем брать (`/api/v2/procedures/?...`, см. gpb_po_slovam.py),
но в СПИСКЕ контактов НЕТ — проверено на живом ответе: атрибуты записи списка это
with_guarantee_application, without_ep, _score, registry_number, stage, title,
platform_url, kind, procedure_type_name, truncated_path, app_guarantee_type,
total_guarantee_application, company_name, company_url, amount, currency_name,
date_published, lot_regions, date_last_update, lots_first_date_begin_auction,
lots_count, template, mineral_type, section_category_name, rebranding_truncated_path,
custom_procedure_type_name, end_registration, guarantee_application_currency,
time_before_end_registration. Ни одного contact_*. Значит карточку надо открывать.

Одиночного публичного JSON-роута карточки НЕТ: /api/v2/procedures/<id> и
/api/v2/procedures/<id>/ отдают 404 (проверено на id 1437130 и 570054, оба реальные).
Карточка — Nuxt 3 с серверным рендером, данные приезжают в <script id="__NUXT_DATA__">
в формате devalue (плоский массив, ссылки — целочисленные индексы). Оттуда и берём:

    pinia -> PROCEDURES_ID_STORE -> procedure -> attributes -> contact_person

ПРИЗНАК «НЕТ ТАКОЙ ЗАКУПКИ». HTTP-статус НЕ отличает: несуществующий номер отдаёт
200 и пустой каркас страницы. Отличает devalue-обёртка поля procedure:
    есть закупка : ["Ref", n]      -> объект {id, type, attributes, relationships}
    нет закупки  : ["EmptyRef", n] -> arr[n] == "null"
Поле _errors.PROCEDURE_ID_REQUEST в ОБОИХ случаях null — по нему судить нельзя.
"""
import json
import re

FIELDS_CONTACT = ['contact_person', 'contact_phone', 'contact_email']
FIELDS_CUSTOMER = ['customer_contact', 'customer_email', 'customer_phone',
                   'customer_address_main']


def _nuxt_array(html):
    """Плоский devalue-массив из <script id="__NUXT_DATA__" type="application/json">."""
    i = html.find('id="__NUXT_DATA__"')
    if i < 0:
        return None
    j = html.find('>', i) + 1
    k = html.find('</script>', j)
    if j <= 0 or k < 0:
        return None
    try:
        return json.loads(html[j:k])
    except ValueError:
        return None


_WRAP = ('Ref', 'ShallowRef', 'Reactive', 'ShallowReactive')


def _resolve(arr, idx, depth=0):
    if depth > 14 or not isinstance(idx, int) or not (0 <= idx < len(arr)):
        return None
    v = arr[idx]
    if isinstance(v, dict):
        return {k: _resolve(arr, i, depth + 1) for k, i in v.items()}
    if isinstance(v, list):
        if v and isinstance(v[0], str):
            if v[0] in _WRAP:
                return _resolve(arr, v[1], depth + 1)
            if v[0] == 'EmptyRef':
                return None
        return [_resolve(arr, i, depth + 1) for i in v]
    return v


def razobrat(html):
    """HTML карточки -> dict. Ключ 'est' различает три исхода честно:
       True  — карточка есть, поля сняты;
       False — карточки нет (площадка вернула procedure=EmptyRef/"null");
       None  — РАЗОБРАТЬ НЕ УДАЛОСЬ (нет __NUXT_DATA__ / не тот формат). Это НЕ «нет
               контакта»: такие строки надо перезапрашивать, а не считать пустыми.
    """
    arr = _nuxt_array(html)
    if arr is None:
        return {'est': None, 'prichina': 'нет блока __NUXT_DATA__'}

    store_idx = None
    for v in arr:
        if isinstance(v, dict) and 'PROCEDURES_ID_STORE' in v:
            store_idx = v['PROCEDURES_ID_STORE']
            break
    if store_idx is None:
        return {'est': None, 'prichina': 'нет PROCEDURES_ID_STORE в payload'}

    store = arr[store_idx]
    if not isinstance(store, dict) or 'procedure' not in store:
        return {'est': None, 'prichina': 'PROCEDURES_ID_STORE без ключа procedure'}

    wrap = arr[store['procedure']]
    if isinstance(wrap, list) and wrap and wrap[0] == 'EmptyRef':
        return {'est': False, 'prichina': 'нет такой закупки (procedure=EmptyRef -> "null")'}

    proc = _resolve(arr, store['procedure'])
    if not isinstance(proc, dict) or not isinstance(proc.get('attributes'), dict):
        return {'est': None, 'prichina': 'procedure есть, но attributes не словарь'}

    a = proc['attributes']
    out = {'est': True, 'api_id': proc.get('id'),
           'platform_id': a.get('platform_id'),
           'registry_number': a.get('registry_number'),
           'section_description': a.get('section_description')}
    for f in FIELDS_CONTACT + FIELDS_CUSTOMER:
        out[f] = a.get(f)

    rel = proc.get('relationships') or {}
    comp = rel.get('company')
    if isinstance(comp, dict) and isinstance(comp.get('attributes'), dict):
        ca = comp['attributes']
        out['company_full_name'] = ca.get('full_name')
        out['company_inn'] = ca.get('inn')
        out['company_kpp'] = ca.get('kpp')
        out['company_fax'] = ca.get('fax')
    return out


_RE_DD = re.compile(
    r'<dt class="procedureCardDl__value procedureCardDl__value--name"[^>]*>'
    r'\s*Контактное лицо\s*</dt>\s*'
    r'<dd class="procedureCardDl__value procedureCardDl__value--desc"[^>]*>(.*?)</dd>',
    re.S)


def razobrat_dom(html):
    """Запасной путь по разметке — на случай, если Nuxt-формат сменится.
    Блок «Сведения об организаторе»: <dl class="procedureCardDl ...">, пары
    <dt class="procedureCardDl__value procedureCardDl__value--name">Контактное лицо</dt>
    <dd class="procedureCardDl__value procedureCardDl__value--desc"><span>ФИО</span></dd>.
    """
    m = _RE_DD.search(html)
    if not m:
        return None
    return re.sub(r'<[^>]+>', '', m.group(1)).replace('\xa0', ' ').strip() or None


if __name__ == '__main__':
    import sys
    for put in sys.argv[1:]:
        h = open(put, encoding='utf-8').read()
        print('=====', put)
        print(json.dumps(razobrat(h), ensure_ascii=False, indent=1))
        print(' dom-запасной:', repr(razobrat_dom(h)))
