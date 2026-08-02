# -*- coding: utf-8 -*-
"""Токен приложения hh.ru и проверка, что 403 действительно снялся.

Владелец завёл приложение hh и дал client_id/secret. До этого api.hh.ru
отдавал с сервера 403 без токена, и мы ходили по публичной выдаче — а она с
серверного IP показывает капчу. Из-за этого «наём в техслужбу» и поиск
техЛПР по вакансиям работали вполсилы.

Проверяется ЖИВЫМ вызовом, а не наличием ключа в окружении: ключ в env и
работающий доступ — разные вещи, и вторую нельзя вывести из первой.

Токен кладётся в panel.env (HH_APP_TOKEN), чтобы остальные ops брали готовый
и не выпрашивали новый на каждый запуск: у hh есть лимит на выдачу токенов.

Запуск: python hh_token.py
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ENV = r'C:\sender\panel.env'
УА = 'prokompressor-enrich/1.0 (kirillrand4@gmail.com)'


def зпр(url, data=None, headers=None, метод=None):
    h = {'User-Agent': УА}
    h.update(headers or {})
    r = urllib.request.Request(url, data=data, headers=h, method=метод)
    with urllib.request.urlopen(r, timeout=60) as о:
        return о.status, о.read().decode('utf-8', 'replace')


def main():
    cid = os.environ.get('HH_CLIENT_ID', '')
    sec = os.environ.get('HH_CLIENT_SECRET', '')
    print(f'client_id в окружении: {"да, " + cid[:6] + "…" if cid else "НЕТ"}')
    if not (cid and sec):
        print('без пары client_id/secret дальше идти незачем')
        return

    # 1. токен приложения: grant_type=client_credentials
    тело = urllib.parse.urlencode({
        'grant_type': 'client_credentials',
        'client_id': cid, 'client_secret': sec}).encode()
    токен = ''
    try:
        код, текст = зпр('https://hh.ru/oauth/token', data=тело,
                         headers={'Content-Type':
                                  'application/x-www-form-urlencoded'})
        д = json.loads(текст)
        токен = д.get('access_token', '')
        print(f'токен получен: код {код}, живёт {д.get("expires_in")} с, '
              f'тип {д.get("token_type")}')
    except urllib.error.HTTPError as e:
        print(f'ТОКЕН НЕ ВЫДАН: HTTP {e.code} '
              f'{e.read().decode("utf-8", "replace")[:200]}')
        return
    except Exception as e:  # noqa: BLE001
        print(f'ТОКЕН НЕ ВЫДАН: {str(e)[:200]}')
        return

    # 2. ЖИВАЯ проверка: тот самый запрос, который раньше давал 403
    for имя, url in (
            ('вакансии по слову «главный энергетик»',
             'https://api.hh.ru/vacancies?text=%D0%B3%D0%BB%D0%B0%D0%B2%D0%BD'
             '%D1%8B%D0%B9+%D1%8D%D0%BD%D0%B5%D1%80%D0%B3%D0%B5%D1%82%D0%B8'
             '%D0%BA&per_page=1'),
            ('работодатель по названию',
             'https://api.hh.ru/employers?text=%D0%A5%D0%B8%D0%BC%D0%BF%D1%80'
             '%D0%BE%D0%BC&per_page=1')):
        # без токена — как было
        try:
            к1, т1 = зпр(url)
            было = f'{к1}, найдено {json.loads(т1).get("found")}'
        except urllib.error.HTTPError as e:
            было = f'HTTP {e.code}'
        except Exception as e:  # noqa: BLE001
            было = str(e)[:60]
        # с токеном
        try:
            к2, т2 = зпр(url, headers={'Authorization': 'Bearer ' + токен})
            стало = f'{к2}, найдено {json.loads(т2).get("found")}'
        except urllib.error.HTTPError as e:
            стало = f'HTTP {e.code} {e.read().decode("utf-8", "replace")[:120]}'
        except Exception as e:  # noqa: BLE001
            стало = str(e)[:60]
        print(f'  {имя}:')
        print(f'    без токена: {было}')
        print(f'    С ТОКЕНОМ:  {стало}')

    # 3. сохранить токен, чтобы не выпрашивать заново
    if токен:
        стр = []
        if os.path.exists(ENV):
            with open(ENV, encoding='utf-8-sig') as ф:
                стр = [л for л in ф.read().splitlines()
                       if not л.strip().startswith('HH_APP_TOKEN=')]
        стр.append('HH_APP_TOKEN=' + токен)
        with open(ENV, 'w', encoding='utf-8', newline='\n') as ф:
            ф.write('\n'.join(стр) + '\n')
            ф.flush()
            os.fsync(ф.fileno())
        print(f'HH_APP_TOKEN записан в panel.env ({len(токен)} символов)')


if __name__ == '__main__':
    main()
