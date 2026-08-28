# -*- coding: utf-8 -*-
"""Увести legal.unsub_base_url с домена, помеченного Касперским.

Стояло https://mail.parsercompressor.online/u — хост не существует, домен
помечен как фишинг (за пиксель открытий, журнал от 05.08). Удалить ключ
нельзя: config._build_legal требует его и валидирует как http(s) — панель не
поднимется. Переводим на настоящий сайт компании и выключаем HTTP-канал
отписки явно, чтобы выключатель было видно, а не подразумевалось умолчанием.
"""
import io
import os
import sys
import time

sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
ПУТЬ = r"C:\sender\sender.yaml"

ЗАМЕНЫ = [
    ('  unsub_base_url: "https://mail.parsercompressor.online/u"\n'
     '  unsub_secret_env: UNSUB_SIGNING_SECRET\n',
     '  # 28.08.2026: тут стоял https://mail.parsercompressor.online/u — хост\n'
     '  # не существует, а домен помечен Касперским как фишинг (за пиксель\n'
     '  # открытий, журнал от 05.08). Удалить ключ нельзя: _build_legal его\n'
     '  # требует и валидирует как http(s), панель не поднимется. Поэтому\n'
     '  # значение уведено на настоящий сайт компании, а HTTP-канал отписки\n'
     '  # выключен явно — в письмо уходит только mailto:.\n'
     '  unsub_base_url: "https://prokompressor.ru/u"\n'
     '  unsub_http_enabled: false\n'
     '  unsub_secret_env: UNSUB_SIGNING_SECRET\n'),
    ('  path: "/o"\n'
     '  # base_url НЕ задан → пиксель/отписка с legal.unsub_base_url\n',
     '  path: "/o"\n'
     '  # base_url задан выше и НЕ трогается: пиксель выключен, а включи его\n'
     '  # кто-нибудь — бить он должен с панельного домена, а не с сайта\n'
     '  # компании. Прежний комментарий («base_url НЕ задан») противоречил\n'
     '  # строке выше и вводил в заблуждение.\n'),
]

т = io.open(ПУТЬ, encoding="utf-8").read()
if "prokompressor.ru/u" in т:
    print("правка уже стоит")
    raise SystemExit(0)
for стар, _ in ЗАМЕНЫ:
    print("якорь найден %d раз: %r" % (т.count(стар), стар.split("\n")[0]))
    if т.count(стар) != 1:
        print("НЕ ОДИН — не трогаю")
        raise SystemExit(1)

if not КАТИТЬ:
    print("\n[сухой прогон] с --katit применю")
    raise SystemExit(0)

было = т
for стар, нов in ЗАМЕНЫ:
    т = т.replace(стар, нов)
бэк = ПУТЬ + ".bak-%d" % int(time.time())
with io.open(бэк, "w", encoding="utf-8", newline="") as f:
    f.write(было); f.flush(); os.fsync(f.fileno())
with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
    f.write(т); f.flush(); os.fsync(f.fileno())

from sender.config import Config                                   # noqa: E402
try:
    c = Config.load(ПУТЬ)
    л = c.legal()
    print("конфиг читается")
    print("   unsub_base_url      = %r" % л.unsub_base_url)
    print("   unsub_http_enabled  = %r" % c.get("legal.unsub_http_enabled", None))
    print("   list_unsub_header   = %r" % c.get("legal.list_unsub_header", None))
    print("   tracking.open_enabled = %r" % c.get("tracking.open_enabled", None))
    print("бэкап: %s" % os.path.basename(бэк))
except Exception as ex:
    with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
        f.write(было); f.flush(); os.fsync(f.fileno())
    print("конфиг перестал читаться, ОТКАТИЛ: %s" % ex)
    raise SystemExit(1)
print("\nпомеченный домен в файле остался только тут:")
for i, с in enumerate(т.split("\n")):
    if "parsercompressor" in с:
        print("   %4d| %s" % (i + 1, с.strip()[:110]))
