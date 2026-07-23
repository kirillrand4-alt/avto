# -*- coding: utf-8 -*-
"""Очередь-демон отправки (потоковый конвейер): забирает kc-queue-*.json с дропа
по одному, шлёт s1 -> s2, прогресс в kc-stream-progress.json. Генератор на стороне
Claude кладёт письма в очередь по мере готовности. Стоп: kc-queue-STOP.json
(демон дочищает очередь и выходит). Жёсткий дедлайн 4 часа. Резюмируемо."""
import os, json, re, time, random, ssl, smtplib, traceback
import urllib.request, urllib.parse
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr, make_msgid, formatdate

DROP_URL = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
DROP_TOKEN = os.environ.get('DROP_TOKEN', '')
SMTP_HOST, SMTP_PORT = 'smtp.yandex.ru', 465
BYLINE_INN = 'ООО «Руспром», ИНН 2221239841'
PROGRESS = 'kc-stream-progress.json'
PACE_MIN, PACE_MAX = 20, 40
DEADLINE_SEC = 4 * 3600


def _u(name):
    return f'{DROP_URL}/' + urllib.parse.quote(name)


def drop_get(name):
    req = urllib.request.Request(_u(name), headers={'X-Drop-Token': DROP_TOKEN})
    return urllib.request.urlopen(req, timeout=90).read()


def drop_put(name, blob):
    if isinstance(blob, str):
        blob = blob.encode('utf-8')
    req = urllib.request.Request(_u(name), data=blob, method='PUT',
                                 headers={'X-Drop-Token': DROP_TOKEN})
    urllib.request.urlopen(req, timeout=90).read()


def drop_del(name):
    try:
        req = urllib.request.Request(_u(name), method='DELETE',
                                     headers={'X-Drop-Token': DROP_TOKEN})
        urllib.request.urlopen(req, timeout=90).read()
    except Exception:
        pass


def drop_list():
    try:
        return json.loads(drop_get('list'))
    except Exception:
        return []


def parse_creds(text):
    lines = [l.strip() for l in text.splitlines()]
    box = {}
    cur = None
    for l in lines:
        m = re.match(r'^(s\d)@', l)
        if m:
            cur = m.group(1)
            box[cur] = {'email': l.split()[0], 'passwords': []}
            continue
        if cur and re.fullmatch(r'[A-Za-z0-9]{8,}', l):
            box[cur]['passwords'].append(l)
    return box


def resolve_smtp_password(email_addr, passwords, ctx):
    last = None
    for pw in passwords:
        try:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=30) as s:
                s.login(email_addr, pw)
            return pw, None
        except Exception as e:  # noqa: BLE001
            last = str(e)[:120]
    return None, last


def build_msg(v, from_email, to_email):
    body = v.get('body', '').rstrip() + f"\nМихаил Лиман\n\n{BYLINE_INN}"
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = Header(v.get('subject', '(без темы)'), 'utf-8')
    msg['From'] = formataddr((str(Header('Михаил Лиман', 'utf-8')), from_email))
    msg['To'] = to_email
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid(domain='mail.parsercompressor.online')
    msg['X-Variation-Id'] = str(v.get('idx'))
    msg['X-Campaign'] = 'kc-stream-v3'
    return msg


def load_progress():
    try:
        return json.loads(drop_get(PROGRESS))
    except Exception:
        return {'sent': [], 'log': []}


def main():
    creds = parse_creds(drop_get('данные-теста.txt').decode('utf-8', 'replace'))
    s1, s2 = creds.get('s1'), creds.get('s2')
    ctx = ssl.create_default_context()
    smtp_pw, err = resolve_smtp_password(s1['email'], s1['passwords'], ctx)
    if not smtp_pw:
        drop_put('campaign-error.txt', f'stream: SMTP-логин не прошёл: {err}')
        return
    prog = load_progress()
    prog['status'] = 'streaming'
    prog['ts'] = time.strftime('%Y-%m-%d %H:%M:%S')
    drop_put(PROGRESS, json.dumps(prog, ensure_ascii=False, indent=1))
    t0 = time.time()
    idle_note = 0
    while time.time() - t0 < DEADLINE_SEC:
        names = [f['name'] for f in drop_list()]
        queue = sorted(n for n in names if re.fullmatch(r'kc-queue-\d+\.json', n))
        stop = 'kc-queue-STOP.json' in names
        if not queue:
            if stop:
                break
            idle_note += 1
            time.sleep(15)
            continue
        name = queue[0]
        try:
            v = json.loads(drop_get(name))
        except Exception:
            drop_del(name)
            continue
        idx = v.get('idx')
        if idx in prog['sent']:
            drop_del(name)
            continue
        entry = {'idx': idx, 'subject': v.get('subject'),
                 'ts': time.strftime('%Y-%m-%d %H:%M:%S')}
        try:
            msg = build_msg(v, s1['email'], s2['email'])
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=60) as smtp:
                smtp.login(s1['email'], smtp_pw)
                smtp.sendmail(s1['email'], [s2['email']], msg.as_string())
            entry['ok'] = True
            prog['sent'].append(idx)
        except Exception as e:  # noqa: BLE001
            entry['ok'] = False
            entry['error'] = str(e)[:160]
        prog['log'].append(entry)
        prog['stats'] = {'sent_ok': sum(1 for x in prog['log'] if x.get('ok')),
                         'failed': sum(1 for x in prog['log'] if not x.get('ok'))}
        try:
            drop_put(PROGRESS, json.dumps(prog, ensure_ascii=False, indent=1))
        except Exception:
            pass
        if entry.get('ok'):
            drop_del(name)
        time.sleep(random.uniform(PACE_MIN, PACE_MAX))
    prog['finished'] = time.strftime('%Y-%m-%d %H:%M:%S')
    drop_put(PROGRESS, json.dumps(prog, ensure_ascii=False, indent=1))
    drop_del('kc-queue-STOP.json')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:  # noqa: BLE001
        try:
            drop_put('campaign-error.txt',
                     f'stream {time.strftime("%H:%M:%S")}\n{e}\n{traceback.format_exc()[:1500]}')
        except Exception:
            pass
