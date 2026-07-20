# -*- coding: utf-8 -*-
"""Ночная тест-рассылка вариаций письма-1 s1 -> s2 (Яндекс 360), 1 письмо раз в 3-5 мин.
Работает на СЕРВЕРЕ (из песочницы SMTP закрыт). Резюмируемо: прогресс на дропе,
при рестарте досылает недосланные. Запускается детач-задачей раннера.

Данные: variations-100.json (с дропа) + данные-теста.txt (креды s1/s2 с дропа)."""
import os, sys, json, re, time, random, ssl, smtplib
import urllib.request
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr, make_msgid, formatdate

DROP_URL = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
DROP_TOKEN = os.environ.get('DROP_TOKEN', '')
SMTP_HOST, SMTP_PORT = 'smtp.yandex.ru', 465
PACE_MIN, PACE_MAX = 180, 300           # 3-5 минут
PROGRESS = 'campaign-progress.json'      # на дропе
BYLINE_INN = 'ООО «Руспром», ИНН 2221239841 · prokompressor.ru'


def drop_get(name):
    req = urllib.request.Request(f'{DROP_URL}/{name}', headers={'X-Drop-Token': DROP_TOKEN})
    return urllib.request.urlopen(req, timeout=90).read()


def drop_put(name, blob):
    if isinstance(blob, str):
        blob = blob.encode('utf-8')
    req = urllib.request.Request(f'{DROP_URL}/{name}', data=blob, method='PUT',
                                 headers={'X-Drop-Token': DROP_TOKEN})
    urllib.request.urlopen(req, timeout=90).read()


def parse_creds(text):
    """Из данные-теста.txt: email -> следующий непустой токен = пароль приложения."""
    lines = [l.strip() for l in text.splitlines()]
    box = {}
    for i, l in enumerate(lines):
        m = re.match(r'^(s\d)@', l)
        if m:
            email = l
            pwd = ''
            for j in range(i + 1, min(i + 4, len(lines))):
                if lines[j] and '@' not in lines[j] and 'пароль' not in lines[j].lower() \
                        and lines[j].lower() != 'sender':
                    pwd = lines[j].replace(' ', '')
                    break
            box[m.group(1)] = {'email': email, 'password': pwd}
    return box


def load_progress():
    try:
        return json.loads(drop_get(PROGRESS))
    except Exception:
        return {'sent': [], 'log': []}


def build_msg(v, from_email, to_email):
    body = (v.get('body', '').rstrip()
            + f"\n\n{BYLINE_INN}\n[отписаться: mailto:{from_email}?subject=unsubscribe]")
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = Header(v.get('subject', '(без темы)'), 'utf-8')
    msg['From'] = formataddr((str(Header('Михаил Лиман', 'utf-8')), from_email))
    msg['To'] = to_email
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid(domain='mail.parsercompressor.online')
    msg['List-Unsubscribe'] = f'<mailto:{from_email}?subject=unsubscribe>'
    msg['X-Variation-Id'] = str(v.get('id'))
    msg['X-Campaign'] = 'night-variations-test'
    return msg


def main():
    variations = json.loads(drop_get('variations-100.json'))
    creds = parse_creds(drop_get('данные-теста.txt').decode('utf-8', 'replace'))
    s1, s2 = creds.get('s1'), creds.get('s2')
    if not s1 or not s1.get('password') or not s2:
        drop_put('campaign-error.txt', f'креды не разобраны: {list(creds)}')
        return
    prog = load_progress()
    sent_ids = set(prog['sent'])
    ctx = ssl.create_default_context()
    total = len(variations)
    for idx, v in enumerate(variations):
        vid = v.get('id')
        if vid in sent_ids:
            continue
        entry = {'id': vid, 'subject': v.get('subject'), 'n': idx + 1}
        try:
            msg = build_msg(v, s1['email'], s2['email'])
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=60) as smtp:
                smtp.login(s1['email'], s1['password'])
                smtp.sendmail(s1['email'], [s2['email']], msg.as_string())
            entry['ok'] = True
            entry['ts'] = time.strftime('%Y-%m-%d %H:%M:%S')
        except Exception as e:  # noqa: BLE001
            entry['ok'] = False
            entry['error'] = str(e)[:160]
            entry['ts'] = time.strftime('%Y-%m-%d %H:%M:%S')
        prog['log'].append(entry)
        if entry.get('ok'):
            prog['sent'].append(vid)
        prog['stats'] = {'sent_ok': sum(1 for x in prog['log'] if x.get('ok')),
                         'failed': sum(1 for x in prog['log'] if not x.get('ok')),
                         'total': total, 'done': len(prog['log'])}
        try:
            drop_put(PROGRESS, json.dumps(prog, ensure_ascii=False, indent=1))
        except Exception:
            pass
        if idx < total - 1:
            time.sleep(random.uniform(PACE_MIN, PACE_MAX))
    prog['finished'] = time.strftime('%Y-%m-%d %H:%M:%S')
    drop_put(PROGRESS, json.dumps(prog, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
