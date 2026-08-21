# -*- coding: utf-8 -*-
"""Агрегированный отчёт DMARC - не отбивка, а настоящий NDR - отбивка.

21.08 отчёт DMARC от snemaservis.ru про наш домен лёг в события как
bounce: он приходит с адреса postmaster@, а по этому признаку
looks_like_dsn относил письмо к отчётам о недоставке целиком. При нулевой
отправке за день панель показывала отбивку, которой не было.

Правило теперь такое: отбивкой считается письмо, у которого есть хоть
что-то от отчёта - адрес недоставки, код SMTP, расширенный статус или
машинная часть message/delivery-status. Пустой разбор без такой улики
отбивкой не считается.
"""
from email.message import EmailMessage

from sender.dsn import dsn_po_strukture, looks_like_dsn, parse_dsn


def _dmarc() -> EmailMessage:
    м = EmailMessage()
    м["From"] = "postmaster@snemaservis.ru"
    м["To"] = "i.lyapin@kompressor-air-trade.ru"
    м["Subject"] = ("Report Domain: kompressor-pro-trade.ru "
                    "Submitter: snemaservis.ru Report-ID: 1a0b08d6")
    м.set_content("This is an aggregate DMARC report from snemaservis.ru\n"
                  "Report domain: kompressor-pro-trade.ru\n")
    return м


def _nastoyashchiy_ndr() -> EmailMessage:
    м = EmailMessage()
    м["From"] = "mailer-daemon@yandex.ru"
    м["Subject"] = "Undelivered Mail Returned to Sender"
    м.set_content("Sorry, we were unable to deliver your message.")
    отчёт = EmailMessage()
    отчёт["Content-Type"] = "message/delivery-status"
    отчёт.set_payload("Final-Recipient: rfc822; nekto@example.ru\n"
                      "Action: failed\nStatus: 5.1.1\n")
    м.make_mixed()
    м.attach(отчёт)
    return м


def test_dmarc_ne_imeet_uliki_v_structure():
    """У отчёта DMARC нет машинной части недоставки."""
    assert dsn_po_strukture(_dmarc()) is False


def test_dmarc_pohozh_no_razbor_pust():
    """«Похоже» он даёт (postmaster@), но вытащить из него нечего.

    Именно на этой паре и держится заслон в imap_watcher: похоже - да,
    данных - ноль, значит не отбивка.
    """
    м = _dmarc()
    assert looks_like_dsn(м, м["Subject"], м.get_content()) is True
    инфо = parse_dsn(м)
    assert not инфо.failed
    assert инфо.smtp_code is None
    assert инфо.status is None


def test_nastoyashchiy_ndr_ostayotsya_otbivkoy():
    """Настоящий отчёт улику имеет и данные отдаёт - его не теряем."""
    м = _nastoyashchiy_ndr()
    assert dsn_po_strukture(м) is True
    инфо = parse_dsn(м)
    assert инфо.status == "5.1.1"
    assert инфо.verdict == "hard"
