# -*- coding: utf-8 -*-
"""Вскрытие штатного клиента шлюза перед правкой: исходник, опоры, чужие пользователи, замер «ДО».

Правим `verify_company._provider_call_stdlib` - функцию, которую зовут четыре модуля.
Поэтому сперва смотрим глазами: полный исходник, как построен `_BEZ_PROXY`, что
импортировано в файле (нужны `socket` и `ssl`), и кто ещё её вызывает - сигнатуру трогать
нельзя.

Замер «ДО» делается ДВАЖДЫ:
  а) при естественном порядке DNS - он плавает, поэтому сам по себе ничего не доказывает;
  б) с ПРИНУДИТЕЛЬНО мёртвым адресом первым - вот это воспроизводимо и сравнимо с «ПОСЛЕ».

Прибор только читает и звонит.
"""
import inspect
import os
import re
import socket
import sys
import time

sys.path.insert(0, r'C:\sender\server')
SERV = r'C:\sender\server'


def ishodnik():
    import verify_company as VC
    print('### ИСХОДНИК _provider_call_stdlib')
    src = inspect.getsource(VC._provider_call_stdlib)
    for i, l in enumerate(src.split('\n'), 1):
        print('%3d| %s' % (i, l[:116]))
    print('\n### СИГНАТУРА: %s' % inspect.signature(VC._provider_call_stdlib))
    print('### модель по умолчанию: %r' % getattr(VC, '_PROVIDER_MODEL', None))

    t = open(os.path.join(SERV, 'verify_company.py'), encoding='utf-8',
             errors='replace').read()
    print('\n### как построен _BEZ_PROXY и что импортировано')
    for i, l in enumerate(t.split('\n'), 1):
        if re.search(r'^\s*(import|from)\s+(socket|ssl|http|urllib|json|time)', l):
            print('  имп %4d| %s' % (i, l[:100]))
        if '_BEZ_PROXY' in l and '=' in l.split('#')[0]:
            print('  опора %4d| %s' % (i, l[:110]))
    print('\n  файл %d знаков' % len(t))


def chuzhie():
    print('\n### КТО ЕЩЁ ЗОВЁТ _provider_call_stdlib (сигнатуру менять нельзя)')
    for imya in sorted(os.listdir(SERV)):
        if not imya.endswith('.py'):
            continue
        try:
            t = open(os.path.join(SERV, imya), encoding='utf-8', errors='replace').read()
        except Exception:  # noqa: BLE001
            continue
        for i, l in enumerate(t.split('\n'), 1):
            if '_provider_call_stdlib' in l:
                print('  %-24s %5d| %s' % (imya, i, l.strip()[:92]))


def zamer_do():
    import verify_company as VC
    print('\n### ЗАМЕР «ДО»')
    ai_nast = socket.getaddrinfo
    ai = ai_nast('router.cheap', 443, socket.AF_INET, socket.SOCK_STREAM)
    print('  DNS сейчас первым отдаёт: %s' % ai[0][4][0])

    print('  -- а) естественный порядок DNS, 5 вызовов --')
    ok = 0
    for i in range(5):
        t0 = time.time()
        try:
            out = VC._provider_call_stdlib('Ответь одним словом: работает')
            ok += 1
            print('     %d: ОТВЕТ %r за %.1f с' % (i + 1, (out or '')[:24], time.time() - t0))
        except Exception as ex:  # noqa: BLE001
            print('     %d: СБОЙ за %.1f с: %s: %s'
                  % (i + 1, time.time() - t0, type(ex).__name__, str(ex)[:90]))
    print('     прошло %d из 5' % ok)

    mertvyy = [x for x in ai if x[4][0].startswith('104.')]
    if not mertvyy:
        print('  -- б) адреса 104.* в выдаче нет, принудительную пробу пропускаю --')
        return
    poryadok = sorted(ai, key=lambda x: 0 if x[4][0].startswith('104.') else 1)
    print('  -- б) ПРИНУДИТЕЛЬНО мёртвый первым %s, 5 вызовов --'
          % [x[4][0] for x in poryadok])

    def podmena(*a, **k):
        return poryadok

    ok2 = 0
    for i in range(5):
        t0 = time.time()
        try:
            socket.getaddrinfo = podmena
            out = VC._provider_call_stdlib('Ответь одним словом: работает')
            ok2 += 1
            print('     %d: ОТВЕТ %r за %.1f с' % (i + 1, (out or '')[:24], time.time() - t0))
        except Exception as ex:  # noqa: BLE001
            print('     %d: СБОЙ за %.1f с: %s: %s'
                  % (i + 1, time.time() - t0, type(ex).__name__, str(ex)[:90]))
        finally:
            socket.getaddrinfo = ai_nast
    print('     прошло %d из 5  <- ЭТО И ЕСТЬ ЗАМЕР «ДО»' % ok2)


if __name__ == '__main__':
    bloki = sys.argv[1:] or ['ishodnik', 'chuzhie', 'zamer']
    if 'ishodnik' in bloki:
        ishodnik()
    if 'chuzhie' in bloki:
        chuzhie()
    if 'zamer' in bloki:
        zamer_do()
    print('\n=== вскрытие клиента закончено ===')
