"""Жалоба на спам — это отчёт ARF, а не слово «спам» в тексте письма.

26.08 ПАО «Лукойл» ответило «данный вопрос не относится к компетенции
службы технической поддержки» и дало три других своих адреса. В их
корпоративном баннере нашлось слово «спам» — письмо ушло в жалобы, адрес
автоматом лёг в стоп-лист, карточки лида не завелось.
"""

import os
import sys
from email.message import EmailMessage

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.imap_watcher import ImapWatcher  # noqa: E402


def _сторож():
    return ImapWatcher.__new__(ImapWatcher)


def _письмо(*, from_addr="kto@zavod.ru", тело="", **заголовки):
    m = EmailMessage()
    m["From"] = from_addr
    m["Subject"] = заголовки.pop("subject", "Re: вопрос")
    for к, з in заголовки.items():
        m[к.replace("_", "-")] = з
    m.set_content(тело)
    return m


def test_slovo_spam_v_tekste_ne_zhaloba():
    """Тот самый случай «Лукойла»."""
    тело = ("Добрый день. Данный вопрос не относится к компетенции службы "
            "технической поддержки. ВНИМАНИЕ: письмо из внешней сети, "
            "не открывайте вложения; о спаме сообщайте в службу поддержки.")
    w = _сторож()
    assert w._is_complaint(_письмо(тело=тело), "Re: вопрос", тело) is False


def test_chelovek_pishet_pro_spam_tozhe_ne_zhaloba():
    тело = "Ваше письмо попало у нас в спам, продублируйте на другой адрес."
    w = _сторож()
    assert w._is_complaint(_письмо(тело=тело), "", тело) is False


def test_arf_otchyot_eto_zhaloba():
    m = EmailMessage()
    m["From"] = "abuse@mail.ru"
    m.set_content("x")
    m.set_type("message/feedback-report")
    w = _сторож()
    assert w._is_complaint(m, "", "x") is True


def test_pismo_so_sluzhebnogo_yashchika_zhalob():
    w = _сторож()
    for адрес in ("abuse@mail.ru", "fbl@corp.mail.ru", "complaints@yandex.ru"):
        assert w._is_complaint(_письмо(from_addr=адрес), "", "") is True, адрес


def test_zagolovok_otchyota_eto_zhaloba():
    w = _сторож()
    assert w._is_complaint(_письмо(Feedback_Type="abuse"), "", "") is True
    assert w._is_complaint(_письмо(X_Loop="abuse@mail.ru"), "", "") is True


def test_mashinnaya_chast_arf_tekstom():
    тело = "Feedback-Type: abuse\nUser-Agent: Mail.Ru\nVersion: 1"
    w = _сторож()
    assert w._is_complaint(_письмо(тело=тело), "", тело) is True


# --- ярлык отбивки ---------------------------------------------------------- #

def test_5_7_1_eto_pravila_servera_a_ne_knopka_spam():
    from sender.sobytiya_slovami import pochemu
    # Форма detail та же, что кладёт разбор DSN: причина живёт в
    # dsn.diagnostic, а не в snippet.
    т = pochemu("bounce", {"dsn": {"failed": ["purchasing@akkermann.ru"],
                                   "diagnostic": "smtp; 550 5.7.1 This message "
                                                 "is blocked due to security "
                                                 "reason"}})
    assert "отклонил по своим правилам" in т
    assert "принял за спам" not in т


def test_nastoyashchiy_spam_verdikt_nazvan_svoim_imenem():
    from sender.sobytiya_slovami import pochemu
    т = pochemu("bounce", {"dsn": {"failed": ["kto@zavod.ru"],
                                   "diagnostic": "smtp; 550 rejected: listed "
                                                 "in dnsbl.spamhaus.org"}})
    assert "спам" in т
