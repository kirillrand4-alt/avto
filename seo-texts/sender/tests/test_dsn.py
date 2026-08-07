"""Разбор отчётов о недоставке (DSN): показания приборов.

Классификация hard/soft/policy проверяется в других наборах; здесь — то, что
попадает оператору в журнал: причина отбивки и SMTP-код.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.dsn import parse_dsn  # noqa: E402

# ---- причина отбивки простым текстом (Mail.ru), 07.08 ---- #

MAILRU_BOUNCE = b"""From: mailer-daemon@corp.mail.ru
To: k.yashin@kompressor-expert.ru
Subject: Mail failure.
Content-Type: text/plain; charset="utf-8"

This message was created automatically by mail delivery software.
A message that you sent could not be delivered to one or more of its
recipients. This is a permanent error. The following address(es) failed:

  omts@prorabka.ru
    550 Message was not accepted -- invalid mailbox.  Local mailbox omts@prorabka.ru is unavailable: user not found

Return-path: <k.yashin@kompressor-expert.ru>
Received: by exim-smtp with esmtpa
  451 code from the attached original transcript
"""


def test_mailru_prichina_iz_tela():
    """Mail.ru не шлёт Diagnostic-Code — причина лежит простым текстом.

    07.08 три отбивки подряд легли в журнал с пустой причиной и без кода:
    оператор видел «отбилось» и ничего больше. Классификация при этом
    отрабатывала (hard по словам «user not found»), то есть дефект был именно
    в показаниях приборов."""
    d = parse_dsn(MAILRU_BOUNCE)
    assert d.verdict == "hard"
    assert "user not found" in d.diagnostic
    assert d.diagnostic.startswith("550 Message was not accepted")
    assert d.smtp_code == 550          # а не 451 из приложенного оригинала


def test_diagnostic_ne_beryotsya_iz_originala():
    """Ниже приложенного оригинала не смотрим: там чужие коды и цитаты."""
    сырое = MAILRU_BOUNCE.replace(
        b"    550 Message was not accepted -- invalid mailbox.  Local mailbox omts@prorabka.ru is unavailable: user not found\n",
        b"")
    d = parse_dsn(сырое)
    assert "451" not in (d.diagnostic or "")
