# -*- coding: utf-8 -*-
"""Проверка существования адреса по SMTP БЕЗ отправки письма (до команды DATA).

Схема на каждый домен:
  1. MX домена;
  2. коннект на MX:25, EHLO, MAIL FROM;
  3. **детект catch-all**: RCPT TO на заведомо несуществующий случайный адрес.
     Принят -> домен отвечает «существует» на что угодно, проверять на нём бессмысленно,
     домен отсекается целиком;
  4. если случайный отклонён -> RCPT TO на проверяемый адрес. Принят -> адрес есть.
  5. QUIT. Команда DATA не отправляется никогда, письмо не уходит.

ВАЖНО, ЧЕГО ЭТОТ МЕТОД НЕ УМЕЕТ (читать до использования результатов):
  - Код 4xx это НЕ «адреса нет». Это greylisting или временный отказ. Корпоративные
    серверы (а у наших целевых заказчиков почта своя, см. engineers-lens/HARVEST-rukovodstvo.md)
    греylist-ят массово. Такой результат — `inconclusive`, его нужно перепроверять позже,
    а не трактовать как отрицательный.
  - Accept-then-bounce: часть серверов принимает любой RCPT, а отбивает уже после приёма
    письма. Такой домен НЕ определяется как catch-all и даёт ложное `exists`.
  - Проверка портит репутацию IP, с которого идёт. Запускать ТОЛЬКО с отдельного адреса,
    никогда с того, с которого потом уходит рассылка.
  - Частые пробы с одного IP приводят к блокировке. Отсюда пауза между доменами.
  - Порт 25 исходящий закрыт у большинства хостеров и в песочнице Claude. Скрипт
    НЕ ПРОГОНЯЛСЯ ни разу: запускать там, где 25-й открыт.

Использование:
    python3 email_probe.py --domain ch-energo.ru --candidates ya.kuryumov,y.kuryumov
    python3 email_probe.py --file candidates.txt --out probe-result.json

Правовое: то, что адрес отвечает, — сведения о конкретном человеке. Результат хранить
вместе с основанием обработки, источником и датой (см. engineers-lens/lens-privyazka.md).
"""
import argparse
import json
import os
import random
import smtplib
import socket
import string
import sys
import time

try:
    import dns.resolver
except ImportError:
    sys.exit('нужен dnspython: pip install dnspython')

# HELO-имя и обратный адрес: должны быть реальными и резолвиться, иначе половина
# серверов отвергнет сессию ещё до RCPT.
HELO = os.environ.get('PROBE_HELO', 'mail.example.com')
MAIL_FROM = os.environ.get('PROBE_FROM', 'postmaster@example.com')

PAUSE_MIN = 4.0   # пауза между доменами, чтобы не словить блокировку
PAUSE_MAX = 9.0


def mx_hosts(domain):
    """MX домена по возрастанию приоритета. Пусто — почты у домена нет."""
    try:
        rr = dns.resolver.resolve(domain, 'MX')
    except Exception:  # noqa: BLE001
        return []
    return [str(r.exchange).rstrip('.') for r in sorted(rr, key=lambda r: r.preference)]


def _rand_local():
    return 'x' + ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(20))


def probe_domain(domain, candidates, timeout=20):
    """Вернуть {'domain','mx','catchall','results':{addr: (code, verdict)},'error'?}.

    verdict: exists | not_exists | inconclusive
    catchall=True -> results не заполняется, проверять бессмысленно.
    """
    out = {'domain': domain, 'mx': None, 'catchall': None, 'results': {}}
    hosts = mx_hosts(domain)
    if not hosts:
        out['error'] = 'нет MX'
        return out
    out['mx'] = hosts[0]

    try:
        srv = smtplib.SMTP(timeout=timeout)
        srv.connect(hosts[0], 25)
        srv.ehlo(HELO)
        srv.mail(MAIL_FROM)
    except (smtplib.SMTPException, socket.error, OSError) as e:
        out['error'] = f'коннект/EHLO: {type(e).__name__}: {str(e)[:120]}'
        return out

    try:
        # 1) детект catch-all
        code, _ = srv.rcpt(f'{_rand_local()}@{domain}')
        out['catchall_code'] = code
        if 200 <= code < 300:
            out['catchall'] = True
            return out
        if 400 <= code < 500:
            # сервер и на мусор отвечает «попробуйте позже» — различить ничего нельзя
            out['catchall'] = None
            out['error'] = f'greylisting (код {code} на случайный адрес), результат недостоверен'
            return out
        out['catchall'] = False

        # 2) кандидаты
        for addr in candidates:
            code, _ = srv.rcpt(addr)
            if 200 <= code < 300:
                verdict = 'exists'
            elif 400 <= code < 500:
                verdict = 'inconclusive'
            else:
                verdict = 'not_exists'
            out['results'][addr] = (code, verdict)
    except (smtplib.SMTPException, socket.error, OSError) as e:
        out['error'] = f'во время RCPT: {type(e).__name__}: {str(e)[:120]}'
    finally:
        try:
            srv.quit()
        except Exception:  # noqa: BLE001
            pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--domain')
    ap.add_argument('--candidates', help='локальные части или полные адреса через запятую')
    ap.add_argument('--file', help='файл, по строке на адрес')
    ap.add_argument('--out')
    a = ap.parse_args()

    by_domain = {}
    if a.file:
        for line in open(a.file, encoding='utf-8'):
            addr = line.strip()
            if addr and '@' in addr:
                by_domain.setdefault(addr.split('@', 1)[1], []).append(addr)
    elif a.domain and a.candidates:
        by_domain[a.domain] = [c if '@' in c else f'{c}@{a.domain}'
                               for c in a.candidates.split(',') if c.strip()]
    else:
        sys.exit('нужен --domain + --candidates либо --file')

    if HELO == 'mail.example.com':
        print('ВНИМАНИЕ: PROBE_HELO/PROBE_FROM не заданы. Многие серверы отвергнут сессию '
              'с несуществующим HELO. Задай реальные значения.', file=sys.stderr)

    report = []
    for i, (dom, addrs) in enumerate(by_domain.items()):
        if i:
            time.sleep(random.uniform(PAUSE_MIN, PAUSE_MAX))
        r = probe_domain(dom, addrs)
        report.append(r)
        if r.get('error'):
            print(f'{dom:28s} ОШИБКА: {r["error"]}')
        elif r['catchall']:
            print(f'{dom:28s} CATCH-ALL — домен отсечён, проверка невозможна')
        else:
            for addr, (code, verdict) in r['results'].items():
                print(f'{addr:40s} {verdict:12s} (SMTP {code})')

    if a.out:
        with open(a.out, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'\nсохранено: {a.out}')


if __name__ == '__main__':
    main()
