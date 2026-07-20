# -*- coding: utf-8 -*-
"""Ночная тест-рассылка вариаций письма-1 s1 -> s2 (Яндекс 360), 1 письмо раз в 3-5 мин.
Работает на СЕРВЕРЕ (из песочницы SMTP закрыт). Резюмируемо: прогресс на дропе,
при рестарте досылает недосланные. Запускается детач-задачей раннера.

Данные: variations-100.json (с дропа) + данные-теста.txt (креды s1/s2 с дропа)."""
import os, sys, json, re, time, random, ssl, smtplib, traceback
import urllib.request, urllib.parse
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr, make_msgid, formatdate

DROP_URL = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
DROP_TOKEN = os.environ.get('DROP_TOKEN', '')
SMTP_HOST, SMTP_PORT = 'smtp.yandex.ru', 465
PACE_MIN, PACE_MAX = 180, 300           # 3-5 минут
PROGRESS = 'campaign-progress.json'      # на дропе
BYLINE_INN = 'ООО «Руспром», ИНН 2221239841 · prokompressor.ru'


def _u(name):
    # URL-энкод имени (кириллица типа 'данные-теста.txt' ломает ASCII-урл urllib)
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


def parse_creds(text):
    """Из данные-теста.txt: у каждого ящика МОЖЕТ быть 2 app-пароля (почта/sender).
    Собираем ВСЕ токены-пароли (8+ симв., алфанум) до следующего s\\d@ — main
    подберёт рабочий для SMTP. box[s1] = {email, passwords:[...]}"""
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
    # обратная совместимость: password = первый кандидат
    for k in box:
        box[k]['password'] = box[k]['passwords'][0] if box[k]['passwords'] else ''
    return box


def resolve_smtp_password(email, passwords, ctx):
    """Подобрать app-пароль, которым проходит SMTP-логин (почта vs sender)."""
    last = None
    for pw in passwords:
        try:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=30) as s:
                s.login(email, pw)
            return pw, None
        except Exception as e:  # noqa: BLE001
            last = str(e)[:120]
    return None, last


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
    # ранний сигнал старта — но НЕ затираем уже отправленные (резюм после рестарта)
    try:
        _p = load_progress()
        _p['status'] = 'starting'
        _p['ts'] = time.strftime('%Y-%m-%d %H:%M:%S')
        drop_put(PROGRESS, json.dumps(_p, ensure_ascii=False))
    except Exception:
        pass
    variations = json.loads(drop_get('variations-100.json'))
    creds = parse_creds(drop_get('данные-теста.txt').decode('utf-8', 'replace'))
    s1, s2 = creds.get('s1'), creds.get('s2')
    if not s1 or not s1.get('passwords') or not s2:
        drop_put('campaign-error.txt', f'креды не разобраны: {list(creds)}')
        return
    ctx = ssl.create_default_context()
    # подобрать рабочий SMTP-пароль s1 (почта vs sender)
    smtp_pw, err = resolve_smtp_password(s1['email'], s1['passwords'], ctx)
    if not smtp_pw:
        drop_put('campaign-error.txt',
                 f'SMTP-логин не прошёл ни одним из {len(s1["passwords"])} паролей: {err}')
        return
    prog = load_progress()
    sent_ids = set(prog['sent'])
    total = len(variations)
    for idx, v in enumerate(variations):
        vid = v.get('id')
        if vid in sent_ids:
            continue
        entry = {'id': vid, 'subject': v.get('subject'), 'n': idx + 1}
        try:
            msg = build_msg(v, s1['email'], s2['email'])
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=60) as smtp:
                smtp.login(s1['email'], smtp_pw)
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
    # раннер (spawn_campaign) уже запускает нас детач-процессом — сами НЕ форкаемся
    # (двойной детач ломался на Windows). Просто крутим main(); фатальную ошибку — на дроп.
    try:
        main()
    except Exception as e:  # noqa: BLE001
        try:
            drop_put('campaign-error.txt',
                     f'{time.strftime("%Y-%m-%d %H:%M:%S")}\n{e}\n{traceback.format_exc()[:1500]}')
        except Exception:
            pass
