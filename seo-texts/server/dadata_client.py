# -*- coding: utf-8 -*-
"""DaData findById/party: ИНН -> официальные реквизиты из ЕГРЮЛ (наименование,
адрес, РУКОВОДИТЕЛЬ ФИО+должность, статус, ОКВЭД) + email/телефон, если DaData их
отдаёт. Бесплатно 10k/день. Токен из env DADATA_TOKEN (кладётся в runner-secrets.env).

stdin: {"companies":[{"inn"}], }
stdout: {"results":[{inn,full_name,address,mgmt_name,mgmt_post,status,okved,
                     emails,phones}], "summary":{...}}"""
import os, sys, json, time
import urllib.request, urllib.error

API = 'https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party'
TOKEN = os.environ.get('DADATA_TOKEN', '')


def _token(args):
    return args.get('dadata_token') or TOKEN


def lookup(inn):
    body = json.dumps({'query': str(inn)}).encode('utf-8')
    req = urllib.request.Request(API, data=body, method='POST', headers={
        'Content-Type': 'application/json', 'Accept': 'application/json',
        'Authorization': f'Token {TOKEN}'})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    sugg = data.get('suggestions') or []
    if not sugg:
        return {'error': 'не найдено в DaData'}
    d = sugg[0].get('data', {})
    mgmt = d.get('management') or {}
    name = (d.get('name') or {})
    addr = (d.get('address') or {})
    okveds = d.get('okved')
    # ПОЛНЫЙ список ОКВЭД (основной + доп) — массив okveds (наличие зависит от тарифа).
    # Каждый элемент: {code, name, type('main'/'additional'), main(bool)}.
    okveds_arr = d.get('okveds') or []
    okveds_all = [{'code': o.get('code'), 'name': (o.get('name') or '')[:70],
                   'main': bool(o.get('main') or o.get('type') == 'main')}
                  for o in okveds_arr if isinstance(o, dict) and o.get('code')]
    return {
        'full_name': name.get('full_with_opf') or name.get('short_with_opf'),
        # ОГРН и КРАТКОЕ имя ЕГРЮЛ отдаёт всегда, а мы их выбрасывали. ОГРН
        # нужен для адреса карточки на checko (без него туда не зайти), а
        # краткое имя — то, которым организацию подписывают в государственных
        # списках; по полному их там не найти.
        'ogrn': d.get('ogrn'),
        'short_name': name.get('short_with_opf'),
        'address': (addr.get('value') if isinstance(addr, dict) else None),
        'mgmt_name': mgmt.get('name'),
        'mgmt_post': mgmt.get('post'),
        'status': (d.get('state') or {}).get('status'),
        'okved': okveds,
        'okveds_all': okveds_all,
        'okveds_count': len(okveds_all),
        # emails/phones — если DaData отдаёт (зависит от данных/тарифа)
        'emails': [e.get('value') for e in (d.get('emails') or []) if e.get('value')],
        'phones': [p.get('value') for p in (d.get('phones') or []) if p.get('value')],
    }


def main():
    try:
        args = json.load(sys.stdin)
    except Exception:
        args = {}
    global TOKEN
    TOKEN = _token(args)
    if not TOKEN:
        json.dump({'error': 'нет DADATA_TOKEN (env или args.dadata_token)'}, sys.stdout, ensure_ascii=False)
        return
    results = []
    for c in args.get('companies', []):
        inn = c.get('inn')
        r = {'inn': inn, 'name': c.get('name')}
        try:
            r.update(lookup(inn))
        except urllib.error.HTTPError as e:
            r['error'] = f'http {e.code}: {e.read()[:80].decode("utf-8","replace")}'
        except Exception as e:  # noqa: BLE001
            r['error'] = f'exc:{str(e)[:80]}'
        results.append(r)
        time.sleep(0.15)  # DaData лимит по частоте — щадящий интервал
    with_mgmt = sum(1 for r in results if r.get('mgmt_name'))
    with_email = sum(1 for r in results if r.get('emails'))
    json.dump({'results': results, 'count': len(results),
               'summary': {'with_mgmt': with_mgmt, 'with_email': with_email}},
              sys.stdout, ensure_ascii=False)


if __name__ == '__main__':
    main()
