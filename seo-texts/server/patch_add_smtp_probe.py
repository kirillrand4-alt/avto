# -*- coding: utf-8 -*-
"""Добавляет в раннер задачу `smtp_probe`: проверка существования адреса без отправки письма.

ЗАЧЕМ. `seo-texts/email_probe.py` написан давно и **не запускался ни разу**: исходящий
порт 25 из песочницы закрыт. Проверить реконструированные адреса нечем, а реконструкция
без проверки — это гарантированные баунсы по тёплой рассылке, то есть удар по репутации
домена отправителя.

ЧТО ДЕЛАЕТ ЗАДАЧА. На каждый домен:
  1. берёт MX;
  2. коннект на MX:25, EHLO, MAIL FROM;
  3. **сначала RCPT на случайный несуществующий адрес** — если он принят, домен отвечает
     «существует» на что угодно, и весь домен помечается `catch_all` и дальше не проверяется;
  4. если случайный отклонён — RCPT на проверяемые адреса;
  5. QUIT. **Команда DATA не отправляется никогда, письмо не уходит.**

ЧЕГО МЕТОД НЕ УМЕЕТ (обязательно к прочтению до использования результата):
  - **4xx это не «адреса нет»**, а greylisting или временный отказ. У наших целевых почта
    своя, а корпоративные серверы грейлистят массово. Такой ответ пишется как
    `inconclusive` и НЕ должен трактоваться как отрицательный.
  - **Accept-then-bounce**: сервер принимает любой RCPT, а отбивает уже после приёма письма.
    Детект catch-all такой домен не ловит, и результат будет ложно-положительным.
  - **Проба портит репутацию IP, с которого идёт.** Это адрес сервера владельца. Если с
    него потом планируется рассылка — сначала подумать, а уже потом запускать.

ОГРАНИЧИТЕЛИ, ЗАШИТЫЕ В ЗАДАЧУ:
  - не более `max_domains` доменов за прогон (по умолчанию 20) и `max_per_domain` адресов
    на домен (по умолчанию 6);
  - случайная пауза 4–9 с между доменами;
  - общий таймаут на домен;
  - только порт 25, только RCPT, никакого DATA.

Установка на сервере владельца:
    & "C:\\Program Files\\Python311\\python.exe" 'C:\\sender\\server\\patch_add_smtp_probe.py'
    nssm restart rusprom-runner      <- ОБЯЗАТЕЛЬНО: меняется ALLOW в job_runner.py

Первый запуск задачи стоит сделать в режиме `"selftest": true` — он только проверит,
открыт ли исходящий 25-й порт, и ничего не будет перебирать.
"""
import os
import py_compile
import shutil
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.environ.get('RUNNER_PATH', os.path.join(DIR, 'job_runner.py'))
TARGET = os.environ.get('SMTP_PATH', os.path.join(DIR, 'smtp_probe.py'))

ALLOW_ANCHOR = "\nALLOW = {"
ALLOW_LINE = "    'smtp_probe': [sys.executable, os.path.join(DIR, 'smtp_probe.py')],"
PULL_ANCHOR = "PULL_ALLOW = {"
PULL_NEW = "PULL_ALLOW = {'smtp_probe.py', "

SRC = r'''# -*- coding: utf-8 -*-
"""Задача раннера: проверить существование адресов по SMTP без отправки письма.

stdin:  {"domains": {"ch-energo.ru": ["ya.kuryumov", "y.kuryumov"]},
         "max_domains": 20, "max_per_domain": 6, "selftest": false,
         "helo": "...", "mail_from": "..."}
stdout: {"ok", "port25_open", "results": [...], "error"?}

Команда DATA не отправляется никогда. Подробности и ограничения метода — в
patch_add_smtp_probe.py и в seo-texts/email_probe.py.
"""
import json
import os
import random
import smtplib
import socket
import string
import sys
import time

HELO = os.environ.get('PROBE_HELO', '')
MAIL_FROM = os.environ.get('PROBE_FROM', '')


def _mx(domain):
    try:
        import dns.resolver
    except ImportError:
        return []
    try:
        rr = dns.resolver.resolve(domain, 'MX')
        return [str(r.exchange).rstrip('.') for r in sorted(rr, key=lambda x: x.preference)]
    except Exception:  # noqa: BLE001
        return []


def _port25_open(host='alt1.gmail-smtp-in.l.google.com'):
    """Дёшево проверить, выпускает ли хостер исходящий 25-й порт."""
    try:
        s = socket.create_connection((host, 25), timeout=12)
        s.close()
        return True
    except Exception:  # noqa: BLE001
        return False


def _rand_local():
    return 'x' + ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(14))


def probe_domain(domain, locals_, helo, mail_from, max_per_domain):
    out = {'domain': domain, 'mx': None, 'catch_all': None, 'addresses': {}}
    hosts = _mx(domain)
    if not hosts:
        out['error'] = 'MX не найден'
        return out
    out['mx'] = hosts[0]
    try:
        srv = smtplib.SMTP(timeout=25)
        srv.connect(hosts[0], 25)
        srv.ehlo(helo)
        srv.mail(mail_from)
    except Exception as e:  # noqa: BLE001
        out['error'] = f'{type(e).__name__}: {str(e)[:90]}'
        return out
    try:
        code, _ = srv.rcpt(f'{_rand_local()}@{domain}')
        out['catch_all'] = (200 <= code < 300)
        if out['catch_all']:
            out['note'] = 'домен принимает любой адрес — проверять бессмысленно'
        else:
            for loc in locals_[:max_per_domain]:
                addr = loc if '@' in loc else f'{loc}@{domain}'
                try:
                    c, msg = srv.rcpt(addr)
                except Exception as e:  # noqa: BLE001
                    out['addresses'][addr] = {'verdict': 'error', 'detail': str(e)[:70]}
                    break
                if 200 <= c < 300:
                    v = 'exists'
                elif 400 <= c < 500:
                    v = 'inconclusive'      # greylisting, НЕ отрицательный ответ
                else:
                    v = 'absent'
                out['addresses'][addr] = {'verdict': v, 'code': c,
                                          'detail': (msg or b'')[:80].decode('utf-8', 'replace')}
                time.sleep(1.5)
    finally:
        try:
            srv.quit()
        except Exception:  # noqa: BLE001
            pass
    return out


def main():
    try:
        args = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        args = {}
    out = {'ok': False}
    helo = args.get('helo') or HELO
    mail_from = args.get('mail_from') or MAIL_FROM

    out['port25_open'] = _port25_open()
    if args.get('selftest'):
        out['ok'] = True
        out['note'] = ('исходящий порт 25 открыт' if out['port25_open']
                       else 'исходящий порт 25 закрыт хостером — проба невозможна')
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if not out['port25_open']:
        out['error'] = 'исходящий порт 25 закрыт — проба невозможна'
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if not helo or not mail_from:
        out['error'] = ('нужны helo и mail_from: без реального резолвящегося имени и '
                        'обратного адреса половина серверов рвёт сессию до RCPT')
        json.dump(out, sys.stdout, ensure_ascii=False)
        return

    domains = args.get('domains') or {}
    max_domains = int(args.get('max_domains', 20))
    max_per_domain = int(args.get('max_per_domain', 6))
    res = []
    for i, (dom, locs) in enumerate(list(domains.items())[:max_domains]):
        if i:
            time.sleep(random.uniform(4.0, 9.0))
        res.append(probe_domain(dom, list(locs or []), helo, mail_from, max_per_domain))
    out['results'] = res
    out['ok'] = True
    json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == '__main__':
    main()
'''


def main():
    with open(TARGET, 'w', encoding='utf-8') as f:
        f.write(SRC)
    try:
        py_compile.compile(TARGET, doraise=True)
    except Exception as e:  # noqa: BLE001
        sys.exit(f'smtp_probe.py не компилируется: {e}')
    print(f'записан {TARGET}')

    if not os.path.exists(RUNNER):
        sys.exit(f'не найден {RUNNER}')
    t = open(RUNNER, encoding='utf-8').read()
    changed = False
    bak = f'{RUNNER}.bak-{int(time.time())}'
    shutil.copy2(RUNNER, bak)

    if "'smtp_probe'" in t:
        print('smtp_probe уже в ALLOW')
    elif t.count(ALLOW_ANCHOR) != 1:
        print(f'якорь ALLOW найден {t.count(ALLOW_ANCHOR)} раз — НЕ ПАТЧУ')
    else:
        t = t.replace(ALLOW_ANCHOR, ALLOW_ANCHOR + '\n' + ALLOW_LINE, 1)
        changed = True

    if "'smtp_probe.py'" in t:
        print('smtp_probe.py уже в PULL_ALLOW')
    elif t.count(PULL_ANCHOR) != 1:
        print(f'якорь PULL_ALLOW найден {t.count(PULL_ANCHOR)} раз — самообновление не подключено')
    else:
        t = t.replace(PULL_ANCHOR, PULL_NEW, 1)
        changed = True

    if changed:
        open(RUNNER, 'w', encoding='utf-8').write(t)
        try:
            py_compile.compile(RUNNER, doraise=True)
        except Exception as e:  # noqa: BLE001
            shutil.copy2(bak, RUNNER)
            sys.exit(f'ОШИБКА КОМПИЛЯЦИИ job_runner, откачен из {bak}: {e}')
        print(f'job_runner пропатчен (бэкап {bak})')
        print('\nНУЖЕН: nssm restart rusprom-runner')
    else:
        os.remove(bak)
        print('job_runner менять не пришлось')


if __name__ == '__main__':
    main()
