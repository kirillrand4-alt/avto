# -*- coding: utf-8 -*-
"""Пароли ящиков КЦ в окружение панели (владелец 14.10: «заведи почты для КЦ»).

Секреты НЕ идут через задание раннера и НЕ печатаются: справку владельца
(CSV: Домен;Адрес;Фамилия;Имя;Отчество;Пароль;env;;Пароль приложения) кладём
на дроп, этот скрипт читает её на сервере, проверяет вход каждого ящика
(SMTP 465 и IMAP 993, сначала паролем приложения, затем основным), пишет
рабочий пароль в C:\\sender\\panel.env (бэкап рядом) под именем env из справки
и ставит AppEnvironmentExtra службы SenderPanel через nssm БЕЗ перезапуска.
После — удаляет CSV с дропа. В вывод: адрес, env, какой пароль подошёл, ок/ошибка.

    kc_yashchiki_paroli.py <имя_файла_на_дропе> [--primenit]
"""
import imaplib
import os
import re
import shutil
import smtplib
import subprocess
import sys
import time

ДРОП = r"C:\seostat\drop\drop-storage"
ENV = r"C:\sender\panel.env"
ПРИМ = "--primenit" in sys.argv
файл = os.path.join(ДРОП, os.path.basename(sys.argv[1]))
строки = open(файл, encoding="utf-8-sig").read().splitlines()
ящики = []
for с in строки[1:]:
    п = с.split(";")
    if len(п) < 9 or "@" not in п[1]:
        continue
    ящики.append({"адрес": п[1].strip().lower(), "env": п[6].strip(), "пароль": п[5].strip(),
                  "прил": п[8].strip()})
print("ящиков в справке: %d" % len(ящики))


def вход(адрес, пароль):
    try:
        s = smtplib.SMTP_SSL("smtp.yandex.ru", 465, timeout=25)
        s.login(адрес, пароль)
        s.quit()
    except Exception as е:  # noqa: BLE001
        return "smtp: " + str(е)[:70]
    try:
        im = imaplib.IMAP4_SSL("imap.yandex.ru", 993, timeout=25)
        im.login(адрес, пароль)
        im.logout()
    except Exception as е:  # noqa: BLE001
        return "imap: " + str(е)[:70]
    return None


значения, ок = {}, 0
for я in ящики:
    итог = None
    for вид, пароль in (("приложения", я["прил"]), ("основной", я["пароль"])):
        if not пароль:
            continue
        ош = вход(я["адрес"], пароль)
        if ош is None:
            итог = вид
            значения[я["env"]] = пароль
            break
        последняя = ош
    if итог:
        ок += 1
        print("  OK  %-46s %-15s пароль %s" % (я["адрес"], я["env"], итог))
    else:
        print("  ОШИБКА %-43s %-15s %s" % (я["адрес"], я["env"], последняя))
print("вход прошёл: %d из %d" % (ок, len(ящики)))

if ПРИМ and значения:
    shutil.copy2(ENV, ENV + ".bak-%d" % int(time.time()))
    старые = open(ENV, encoding="utf-8-sig").read().splitlines()
    оставить = [л for л in старые if not any(л.strip().startswith(к + "=") for к in значения)]
    слитые = оставить + ["%s=%s" % (к, в) for к, в in значения.items()]
    with open(ENV, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(слитые) + "\n")
    чистые = []
    for л in слитые:
        л = л.strip()
        if not л or л.startswith("#") or "=" not in л:
            continue
        к, _, в = л.partition("=")
        в = re.sub(r"\s+#.*$", "", в).strip()
        if к.strip() and в:
            чистые.append("%s=%s" % (к.strip(), в))
    nssm = shutil.which("nssm")
    for кандидат in (r"C:\nssm\nssm.exe", r"C:\nssm\win64\nssm.exe", r"C:\tools\nssm\nssm.exe",
                     r"C:\nssm-2.24\win64\nssm.exe"):
        if not nssm and os.path.exists(кандидат):
            nssm = кандидат
    if nssm:
        р = subprocess.run([nssm, "set", "SenderPanel", "AppEnvironmentExtra", "\r\n".join(чистые)],
                           capture_output=True, text=True, timeout=60)
        print("nssm AppEnvironmentExtra: rc=%s (служба НЕ перезапущена)" % р.returncode)
    else:
        print("nssm не найден — panel.env записан, окружение службы не обновлено")
    print("в panel.env записано переменных: %d" % len(значения))
    os.remove(файл)
    print("справка удалена с дропа")
print("=== ЯЩИКИ КЦ: ПАРОЛИ: %s ===" % ("ПРИМЕНЕНО" if ПРИМ else "только проверка входа"))
