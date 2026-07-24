#!/usr/bin/env python3
"""Живой смоук ящиков — ТОЛЬКО на боевом сервере (нужен открытый 465/993).

Для КАЖДОГО ящика из config.mailboxes():
  1. SMTP-логин (провайдер принял логин + пароль приложения);
  2. IMAP-логин (входящие доступны — автоответчик сможет читать);
  3. опц. --send <адрес> — отправить одно тест-письмо на контрольный ящик
     (проверить реальную доставку/инбокс/подпись/пиксель ГЛАЗАМИ).

⛔ Без --send ничего не отправляется — только проверка аутентификации.
С --send письма уходят ТОЛЬКО на указанный контрольный адрес (свой ящик),
НЕ по базе. Это ручная проверка оператора, не рассылка.

Пароли берутся из env по mailbox.password_env (panel.env). Запуск:
  python3 sender/tools/smoke_boxes_live.py --config /opt/sender/config.yaml
  python3 sender/tools/smoke_boxes_live.py --config ... --send you@yandex.ru
"""
import argparse
import imaplib
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.config import Config  # noqa: E402


def _smtp_login(mb) -> str:
    pw = os.environ.get(mb.password_env, "")
    if not pw:
        return f"нет пароля в env {mb.password_env}"
    try:
        ctx = ssl.create_default_context()
        if mb.smtp_port == 465:
            cl = smtplib.SMTP_SSL(mb.smtp_host, mb.smtp_port, timeout=20,
                                  context=ctx)
        else:
            cl = smtplib.SMTP(mb.smtp_host, mb.smtp_port, timeout=20)
            cl.starttls(context=ctx)
            cl.ehlo()
        cl.login(mb.login, pw)
        cl.quit()
        return "OK"
    except smtplib.SMTPAuthenticationError as e:
        return f"АВТОРИЗАЦИЯ ОТКЛОНЕНА: {e.smtp_code} {e.smtp_error[:80]}"
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e}"


def _imap_login(mb) -> str:
    pw = os.environ.get(mb.password_env, "")
    if not pw:
        return f"нет пароля в env {mb.password_env}"
    try:
        cl = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port)
        cl.login(mb.login, pw)
        cl.select("INBOX", readonly=True)
        cl.logout()
        return "OK"
    except imaplib.IMAP4.error as e:
        return f"IMAP ОТКЛОНИЛ: {e}"
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e}"


def _send_test(mb, to_addr: str) -> str:
    pw = os.environ.get(mb.password_env, "")
    msg = EmailMessage()
    msg["From"] = f"{mb.from_name} <{mb.mailbox_id}>"
    msg["To"] = to_addr
    msg["Subject"] = f"Смоук доставки [{mb.mailbox_id}]"
    msg.set_content(
        f"Тест доставки с ящика {mb.mailbox_id}.\n"
        f"Проверь: инбокс/спам, From, SPF/DKIM/DMARC=pass в свойствах письма.\n"
        f"--\nООО «Руспром», ИНН 2221239841")
    try:
        ctx = ssl.create_default_context()
        cl = smtplib.SMTP_SSL(mb.smtp_host, mb.smtp_port, timeout=20,
                              context=ctx)
        cl.login(mb.login, pw)
        cl.send_message(msg)
        cl.quit()
        return "отправлено"
    except Exception as e:  # noqa: BLE001
        return f"НЕ отправлено: {type(e).__name__}: {e}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", required=True)
    ap.add_argument("--send", metavar="EMAIL",
                    help="отправить тест-письмо на этот КОНТРОЛЬНЫЙ адрес")
    args = ap.parse_args()

    cfg = Config.load(args.config)
    boxes = list(cfg.mailboxes())
    print(f"ящиков в конфиге: {len(boxes)}"
          + (f"; тест-письма → {args.send}" if args.send else ""))
    bad = 0
    for mb in boxes:
        smtp = _smtp_login(mb)
        imap = _imap_login(mb)
        line = f"{mb.mailbox_id:40} SMTP:{smtp:12} IMAP:{imap}"
        if args.send and smtp == "OK":
            line += f"  send:{_send_test(mb, args.send)}"
        mark = "OK " if (smtp == "OK" and imap == "OK") else "!! "
        bad += 0 if (smtp == "OK" and imap == "OK") else 1
        print(mark + line)
    print(f"\nитого: {len(boxes) - bad}/{len(boxes)} ящиков логинятся")
    if args.send:
        print("Проверь контрольный ящик: инбокс/спам, в свойствах письма "
              "SPF=pass, DKIM=pass (домен ящика), DMARC=pass.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
