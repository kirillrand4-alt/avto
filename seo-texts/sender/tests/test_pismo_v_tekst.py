# -*- coding: utf-8 -*-
"""Лента переписки показывала исходник письма вместо письма.

Скриншот владельца 18.08: в карточке лида вместо ответа клиента видно
«<div>Кому: dver-metall@yandex.ru<br /></div>», «&lt;k.yashin@…&gt;» и
куски CSS. Тело приходит HTML-ом, а лента печатает его как обычный текст.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.pismo_v_tekst import pohozhe_na_html, v_tekst  # noqa: E402

ПИСЬМО = (
    '<div>----------------</div>\n'
    '<div>Кому: dver-metall@yandex.ru (dver-metall@yandex.ru);<br /></div>\n'
    '<div>Тема: Вопрос по компрессорному парку в «Барос»;<br /></div>\n'
    '<div>18.08.2026, 09:31, "Кирилл Яшин, КомпрессорЦентр" '
    '&lt;k.yashin@kompressor-pro-expert.ru&gt;:<br /></div>\n'
    '<blockquote><p>Добрый день!<br /><br />На производствах металлических '
    'дверей сжатый воздух нужен для пескоструя.<br /><br />С уважением,<br />'
    'Кирилл Яшин<br />ООО «Руспром», ИНН <span class="wmi-callto">2221239841'
    '</span><br /></p></blockquote>'
    '<div style="background-color:rgb( 255 , 255 , 255 );color:rgb( 0 , 0 , 0 )'
    ';font-family:\'arial\' , \'tahoma\';font-size:15px"><em><span '
    'style="color:rgb( 178 , 34 , 34 )"><strong>Переписка по заказам '
    'рассматривается как официальный документ.</strong></span></em></div>'
)


def test_tegov_v_vyvode_net():
    т = v_tekst(ПИСЬМО)
    assert "<div>" not in т and "<br" not in т and "blockquote" not in т, т[:200]


def test_soderzhanie_ostalos():
    т = v_tekst(ПИСЬМО)
    for кусок in ("Кому: dver-metall@yandex.ru", "Добрый день!",
                  "пескоструя", "ООО «Руспром», ИНН 2221239841",
                  "официальный документ"):
        assert кусок in т, f"потеряно: {кусок}\n---\n{т}"


def test_adres_v_uglovyh_skobkah_ne_syel_tegi():
    """«&lt;адрес&gt;» — это адрес, а не тег: снимаем теги ДО раскодирования."""
    т = v_tekst(ПИСЬМО)
    assert "<k.yashin@kompressor-pro-expert.ru>" in т, т[:300]


def test_stili_ne_lezut_v_tekst():
    т = v_tekst(ПИСЬМО)
    assert "background-color" not in т and "font-family" not in т, т[:300]


def test_plain_text_ne_trogaem():
    """Наши письма — обычный текст. Ни одного символа менять нельзя."""
    п = ("Добрый день, Илья!\n\nСмотрел профиль «Барос».\n\n"
         "С уважением,\nКирилл Яшин\nООО «Руспром», ИНН 2221239841")
    assert v_tekst(п) == п
    assert pohozhe_na_html(п) is False


def test_pustoe_i_none():
    assert v_tekst(None) == ""
    assert v_tekst("") == ""


def test_style_blok_vyrezan_celikom():
    т = v_tekst("<style>.a{color:red}</style><p>Текст письма</p>")
    assert т == "Текст письма", repr(т)


def test_dvoynoy_sloy_razmetki():
    """Цитата часто несёт свой же исходник экранированным — чистим и его."""
    т = v_tekst("<div>Ответ:&lt;p&gt;Здравствуйте&lt;/p&gt;</div>")
    assert "<p>" not in т and "Здравствуйте" in т, repr(т)


def test_ne_slipayutsya_stroki():
    т = v_tekst("<div>первая</div><div>вторая</div>")
    assert т == "первая\nвторая", repr(т)


def test_neразрывный_probel():
    т = v_tekst("<p>слово&nbsp;слово</p>")
    assert т == "слово слово", repr(т)


def test_pochtovyy_ekran_odnochastnoe_html():
    """Письмо из одной части бывает HTML-ом — экран почты показывал исходник.

    В mailbrowser ветка снятия тегов работала только для multipart; письмо
    без частей приезжало в панель как есть.
    """
    import email
    from sender.mailbrowser import MailBrowser
    # ИЗ БАЙТОВ, а не из строки: get_payload(decode=True) на письме,
    # разобранном из str, кодирует кириллицу через raw-unicode-escape и
    # отдаёт «\u0414...» — ловушка стандартной библиотеки, не наша.
    сырое = email.message_from_bytes(
        "Subject: Тест\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
        "<div>Добрый день!<br />Ответим завтра.</div>".encode())
    b = MailBrowser.__new__(MailBrowser)
    b._parse_headers = lambda uid, m, seen=False: {"uid": uid}
    тело = b._parse_full("1", сырое)["body"]
    assert тело == "Добрый день!\nОтветим завтра.", repr(тело)


def _pismo(сырое: str):
    import email
    from sender.imap_watcher import ImapWatcher
    w = ImapWatcher.__new__(ImapWatcher)
    return w._extract_body(email.message_from_bytes(сырое.encode()))


def test_vhodyashchee_iz_odnoy_chasti_html():
    """Так пришёл ответ, который владелец увидел разметкой в карточке лида."""
    т = _pismo("Subject: Re\r\nContent-Type: text/html; charset=utf-8\r\n"
               "\r\n<div>Присылайте информацию на info@hoger.pro</div>"
               "<div style=\"color:rgb( 26 , 26 , 26 )\">С уважением</div>")
    assert "<div" not in т and "rgb(" not in т, т
    assert "Присылайте информацию на info@hoger.pro" in т


def test_mnogochastnoe_bez_tekstovoy_chasti():
    """Половина почтовых клиентов шлёт только HTML — текст терялся целиком."""
    сырое = (
        "Subject: Re\r\n"
        "Content-Type: multipart/alternative; boundary=BB\r\n\r\n"
        "--BB\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
        "<p>Спасибо, посмотрим</p>\r\n--BB--\r\n")
    assert _pismo(сырое) == "Спасибо, посмотрим", repr(_pismo(сырое))


def test_tekstovaya_chast_v_prioritete():
    сырое = (
        "Subject: Re\r\n"
        "Content-Type: multipart/alternative; boundary=BB\r\n\r\n"
        "--BB\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n"
        "чистый текст\r\n"
        "--BB\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
        "<p>разметка</p>\r\n--BB--\r\n")
    assert _pismo(сырое) == "чистый текст"


def test_otchyot_o_nedostavke_ne_postradal():
    """DSN приходит обычным текстом — разбор его не трогает."""
    т = _pismo("Subject: Undelivered\r\nContent-Type: text/plain\r\n\r\n"
               "550 Message was not accepted -- invalid mailbox.")
    assert т == "550 Message was not accepted -- invalid mailbox."


ТЕСТЫ = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    сбои = []
    for т in ТЕСТЫ:
        try:
            т()
            print(f"  ок   {т.__name__}")
        except Exception as ex:                                # noqa: BLE001
            сбои.append(т.__name__)
            print(f"  СБОЙ {т.__name__}: {type(ex).__name__} {str(ex)[:200]}")
    print(f"\n{len(ТЕСТЫ) - len(сбои)} прошло, {len(сбои)} упало")
    sys.exit(1 if сбои else 0)
