# -*- coding: utf-8 -*-
r"""fixBX (14.10): проверка вебхука Битрикс24 БЕЗ ЗАПИСИ – что он умеет.

Владелец положил ссылку входящего вебхука на дроп (bitrix-webhook.txt). Скрипт:
  1. забирает ссылку в настройки сервера C:\centro2\data\bitrix-webhook.secret (не в репозиторий, не на дроп),
     файл с дропа удаляет; ссылка нигде не печатается (только домен портала);
  2. вызывает только читающие методы: scope (права вебхука), profile (чей вебхук), crm.lead.fields (поля лида,
     в т. ч. свои UF_…), crm.status.list по источникам лида, crm.lead.list – только число лидов; если права есть –
     crm.deal.fields, crm.category.list по сделкам (воронки), crm.requisite.fields (есть ли ИНН в реквизитах).
Ничего не создаёт и не меняет.

    python3 zapusk_na_servere.py fixBX_proverka.py
"""
import io
import json
import os
import re
import urllib.parse
import urllib.request

DROP_F = next((p for p in (r'C:\seostat\drop\drop-storage\bitrix-webhook.txt', r'C:\seostat\drop\drop-storage\bitrix-webhook.txt.txt') if os.path.exists(p)), r'C:\seostat\drop\drop-storage\bitrix-webhook.txt')
SEKRET = r'C:\centro2\data\bitrix-webhook.secret'


def baza():
    if os.path.exists(DROP_F):
        s = io.open(DROP_F, encoding='utf-8-sig').read().strip()
        m = re.search(r'https://[^\s"\'<>]+/rest/\d+/[A-Za-z0-9]+/?', s)
        if not m:
            raise SystemExit('в bitrix-webhook.txt не найдена ссылка вида https://…/rest/<id>/<код>/')
        u = m.group(0).rstrip('/') + '/'
        io.open(SEKRET, 'w', encoding='utf-8').write(u)
        os.remove(DROP_F)
        print('ссылка забрана в настройки сервера, файл с дропа удалён')
    if not os.path.exists(SEKRET):
        raise SystemExit('ссылки нет ни на дропе, ни в настройках сервера')
    return io.open(SEKRET, encoding='utf-8').read().strip()


import builtins  # noqa: E402
_VYVOD = []
_print = builtins.print


def print(*a, **k):  # noqa: A001 – весь вывод ещё и в файл на дроп (вывод запуска обрезается)
    _VYVOD.append(' '.join(str(x) for x in a))
    _print(*a, **k)


B = baza()
print('портал:', urllib.parse.urlparse(B).hostname)


def vyzov(metod, **params):
    q = urllib.parse.urlencode(params, doseq=True)
    try:
        with urllib.request.urlopen(B + metod + '.json' + ('?' + q if q else ''), timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode('utf-8'))
        except Exception:  # noqa: BLE001
            return {'error': 'HTTP %s' % e.code}
    except Exception as e:  # noqa: BLE001
        return {'error': repr(e)[:200]}


def oshibka(o):
    return o.get('error') and '%s: %s' % (o.get('error'), (o.get('error_description') or '')[:150])


o = vyzov('scope')
print('\nправа вебхука (scope):', oshibka(o) or o.get('result'))
o = vyzov('profile')
r = o.get('result') or {}
print('вебхук от имени:', oshibka(o) or '%s %s (id %s, админ: %s)' % (r.get('NAME'), r.get('LAST_NAME'), r.get('ID'), r.get('ADMIN')))

o = vyzov('crm.lead.fields')
if oshibka(o):
    print('\ncrm.lead.fields:', oshibka(o))
else:
    f = o['result']
    print('\nполя лида: %d' % len(f))
    for k, v in f.items():
        nazv = v.get('formLabel') or v.get('listLabel') or v.get('title') or ''
        print('  %-28s %-12s %s%s%s' % (k, v.get('type'), nazv, ' [обяз.]' if v.get('isRequired') else '',
                                         ' [только чтение]' if v.get('isReadOnly') else ''))
o = vyzov('crm.status.list', **{'filter[ENTITY_ID]': 'SOURCE'})
print('\nисточники лида:', oshibka(o) or ['%s=%s' % (x['STATUS_ID'], x['NAME']) for x in o.get('result', [])])
o = vyzov('crm.lead.list', **{'select[]': 'ID', 'order[ID]': 'DESC'})
print('лидов в CRM (видно вебхуку):', oshibka(o) or o.get('total'))

o = vyzov('crm.deal.fields')
print('\ncrm.deal.fields:', oshibka(o) or 'доступно, полей %d' % len(o.get('result', {})))
o = vyzov('crm.category.list', entityTypeId=2)
print('воронки сделок:', oshibka(o) or ['%s=%s' % (c.get('id'), c.get('name')) for c in (o.get('result') or {}).get('categories', [])])
o = vyzov('crm.requisite.fields')
print('реквизиты (ИНН):', oshibka(o) or ('RQ_INN есть' if 'RQ_INN' in (o.get('result') or {}) else 'поля RQ_INN нет'))
o = vyzov('crm.company.list', **{'select[]': 'ID'})
print('компаний в CRM (видно вебхуку):', oshibka(o) or o.get('total'))
o = vyzov('user.search', **{'FILTER[ACTIVE]': 'true'})
print('пользователи (для ответственных):', oshibka(o) or 'доступно, найдено %s' % o.get('total'))

io.open(r'C:\seostat\drop\drop-storage\fixBX-proverka.txt', 'w', encoding='utf-8').write('\n'.join(_VYVOD))

# ---- дополнительно (тоже только чтение): стадии лида, «Группа товара (MEYER)», почему не видно число лидов
o = vyzov('crm.status.list', **{'filter[ENTITY_ID]': 'STATUS'})
print('\nстадии лида:', oshibka(o) or ['%s=%s' % (x['STATUS_ID'], x['NAME']) for x in o.get('result', [])])
o = vyzov('crm.lead.fields')
gt = ((o.get('result') or {}).get('UF_CRM_1711628077') or {}).get('items') or []
print('Группа товара (MEYER):', ['%s=%s' % (x.get('ID'), x.get('VALUE')) for x in gt])
o = vyzov('crm.lead.list', **{'select[]': 'ID', 'order[ID]': 'DESC'})
print('crm.lead.list: ключи ответа %s, строк %s, ошибка %s' % (sorted(o.keys()), len(o.get('result') or []), oshibka(o)))
io.open(r'C:\seostat\drop\drop-storage\fixBX-proverka.txt', 'w', encoding='utf-8').write('\n'.join(_VYVOD))
