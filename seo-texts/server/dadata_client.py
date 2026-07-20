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
    return {
        'full_name': name.get('full_with_opf') or name.get('short_with_opf'),
        'address': (addr.get('value') if isinstance(addr, dict) else None),
        'mgmt_name': mgmt.get('name'),
        'mgmt_post': mgmt.get('post'),
        'status': (d.get('state') or {}).get('status'),
        'okved': okveds,
        # emails/phones — если DaData отдаёт (зависит от данных/тарифа)
        'emails': [e.get('value') for e in (d.get('emails') or []) if e.get('value')],
        'phones': [p.get('value') for p in (d.get('phones') or []) if p.get('value')],
    }


def main():
    if not TOKEN:
        json.dump({'error': 'нет DADATA_TOKEN в env (добавь в runner-secrets.env)'},
                  sys.stdout, ensure_ascii=False)
        return
    try:
        args = json.load(sys.stdin)
    except Exception:
        args = {}
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
