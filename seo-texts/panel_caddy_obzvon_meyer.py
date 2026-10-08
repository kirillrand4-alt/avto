# -*- coding: utf-8 -*-
"""Публикация копии наружу: маршрут /obzvon-meyer в Caddy на порт 8016.

ПОРЯДОК, КОТОРЫЙ НЕЛЬЗЯ МЕНЯТЬ: бэкап -> правка -> validate -> и только потом reload.
На 80/443 висит один Caddy на все сайты владельца (parsercompressor.online, zernosort.ru,
sort-inspection.ru, панель, редиректы доменов-двойников). Битый конфиг уронил бы их все,
поэтому при неудачной проверке файл возвращается из бэкапа и перезагрузки не происходит.

Почему /obzvon-meyer не конфликтует с /obzvon: матчер «path /obzvon /obzvon/*» не ловит
/obzvon-meyer, потому что следующий знак дефис, а не слэш. Проверяется замером после
перезагрузки: боевой /obzvon/centro обязан отвечать как раньше.
"""
import io
import os
import re
import shutil
import ssl
import subprocess
import time
import urllib.error
import urllib.request

KONF = r'C:\Caddyfile'
CADDY = r'C:\caddy.exe'
PORT = 8016
PUT = '/obzvon-meyer'
itog = []


def skazat(s):
    itog.append(str(s))
    print(s)


ishod = io.open(KONF, encoding='utf-8', errors='replace').read()
skazat('Caddyfile: %d знаков' % len(ishod))
if PUT in ishod:
    skazat('маршрут %s в конфиге УЖЕ есть — конфиг не правлю' % PUT)
    pravka_nuzhna = False
else:
    pravka_nuzhna = True

# --- ищем блок боевого обзвона, чтобы встать рядом и в том же стиле
m = re.search(
    r'([ \t]*)@obzvon\s+path\s+/obzvon\s+/obzvon/\*\s*\n'
    r'[ \t]*handle\s+@obzvon\s*\{\s*\n'
    r'[ \t]*reverse_proxy\s+127\.0\.0\.1:8012\s*\n'
    r'[ \t]*\}\s*\n', ishod)
if not m:
    skazat('ЯКОРЬ НЕ НАЙДЕН: блок @obzvon в ожидаемом виде отсутствует.'
           ' Конфиг не меняю — руками надёжнее, чем вслепую.')
    pravka_nuzhna = False
else:
    otstup = m.group(1)
    skazat('блок @obzvon найден на позиции %d, отступ %r' % (m.start(), otstup))

if pravka_nuzhna:
    rezerv = KONF + time.strftime('.bak-%Y%m%d-%H%M%S')
    shutil.copy2(KONF, rezerv)
    skazat('бэкап: %s' % rezerv)

    # Точный путь обрабатывается ПЕРВЫМ: handle-блоки взаимоисключающие и идут по
    # порядку, поэтому если сначала поставить звёздочку, она же поймает и короткий
    # адрес, и редиректа не случится.
    blok = (
        '%s# --- Обзвон Мейера: ОТДЕЛЬНАЯ копия панели со своей базой, порт %d.\n'
        '%s# Боевой обзвон остаётся на /obzvon (8012), старые базы kc и meyer тоже.\n'
        '%shandle %s {\n'
        '%s        redir * %s/centro\n'
        '%s}\n'
        '%s@obzvon_meyer path %s/*\n'
        '%shandle @obzvon_meyer {\n'
        '%s        reverse_proxy 127.0.0.1:%d\n'
        '%s}\n'
        % (otstup, PORT, otstup, otstup, PUT, otstup, PUT, otstup,
           otstup, PUT, otstup, otstup, PORT, otstup))
    novyy = ishod[:m.end()] + blok + ishod[m.end():]
    io.open(KONF, 'w', encoding='utf-8').write(novyy)
    skazat('блок вставлен, стало %d знаков (+%d)' % (len(novyy), len(novyy) - len(ishod)))

    # --- проверка ДО перезагрузки
    pr = subprocess.run([CADDY, 'validate', '--config', KONF],
                        capture_output=True, timeout=300)
    vyh = (pr.stdout + pr.stderr).decode('utf-8', 'replace')
    skazat('validate rc=%s' % pr.returncode)
    for l in vyh.strip().splitlines()[-6:]:
        skazat('   %s' % l.strip()[:160])
    if pr.returncode != 0:
        shutil.copy2(rezerv, KONF)
        skazat('ПРОВЕРКА НЕ ПРОШЛА — файл возвращён из бэкапа, reload НЕ делаю')
        print('\n===== ИТОГ =====')
        for s in itog:
            print(s)
        raise SystemExit(1)

    pr = subprocess.run([CADDY, 'reload', '--config', KONF],
                        capture_output=True, timeout=300, cwd=r'C:\\')
    vyh = (pr.stdout + pr.stderr).decode('utf-8', 'replace')
    skazat('reload rc=%s' % pr.returncode)
    for l in vyh.strip().splitlines()[-6:]:
        skazat('   %s' % l.strip()[:160])
    if pr.returncode != 0:
        shutil.copy2(rezerv, KONF)
        subprocess.run([CADDY, 'reload', '--config', KONF],
                       capture_output=True, timeout=300, cwd=r'C:\\')
        skazat('RELOAD НЕ УДАЛСЯ — конфиг возвращён из бэкапа и перезагружен обратно')
        print('\n===== ИТОГ =====')
        for s in itog:
            print(s)
        raise SystemExit(1)
    time.sleep(3)

# ---------------------------------------------------------------- проверка снаружи
skazat('')
skazat('--- через Caddy по настоящему адресу')
ctx = ssl.create_default_context()


class BezRedirekta(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


op = urllib.request.build_opener(BezRedirekta,
                                 urllib.request.HTTPSHandler(context=ctx))
for put in (PUT, PUT + '/centro', PUT + '/centro/login', PUT + '/centro/stats',
            '/obzvon/centro', '/obzvon/meyer', '/stat'):
    url = 'https://parsercompressor.online' + put
    try:
        o = op.open(url, timeout=30)
        skazat('   %-30s -> %s, %d байт' % (put, o.status, len(o.read())))
    except urllib.error.HTTPError as e:
        skazat('   %-30s -> %s%s' % (put, e.code,
               ('  Location=' + (e.headers.get('Location') or ''))
               if e.headers.get('Location') else ''))
    except Exception as e:  # noqa: BLE001
        skazat('   %-30s -> ОШИБКА %s' % (put, str(e)[:70]))

print('\n===== ИТОГ =====')
for s in itog:
    print(s)
