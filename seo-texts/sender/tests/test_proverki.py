"""Значки проверок у письма: зелёное только за пройденную проверку.

Владелец 11.08: «сделай у каждой почты галочки проверок, с расшифровкой».
Главное правило, которое здесь защищается: галка ставится за ПРОЙДЕННУЮ
проверку, а не за отсутствие плохих новостей. Непроверенный адрес — серый
вопрос, а не галка: «мы не знаем» и «всё хорошо» в интерфейсе путать нельзя,
иначе оператор отправит письмо, думая, что его проверили.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.proverki import (ЛЕГЕНДА, ПОРЯДОК, провайдер_по_mx,  # noqa: E402
                             проверки_письма)


def _по(итог):
    return {p["код"]: p["статус"] for p in итог["punkty"]}


def test_vsyo_proydeno():
    итог = проверки_письма(email="snab@zavod.ru", inn="77", mx_provider="yandex",
                           вердикт_пробы="есть", в_стоп_листе=None,
                           вердикт_гейта="покупатель")
    assert итог["itogo"] == "ok"
    assert set(_по(итог).values()) == {"ok"}
    assert [p["код"] for p in итог["punkty"]] == list(ПОРЯДОК)


def test_neproverennoe_ne_galka():
    """Адрес не проверялся и компанию не судили — это НЕ «всё хорошо»."""
    итог = проверки_письма(email="x@zavod.ru", inn=None, mx_provider="mailru",
                           вердикт_пробы=None, в_стоп_листе=None,
                           вердикт_гейта=None)
    п = _по(итог)
    assert п["proba"] == "net" and п["gejt"] == "net"
    assert итог["itogo"] == "net"


def test_prinimaet_vsyo_ne_podtverzhdenie():
    итог = проверки_письма(email="kk@vebfabrika.ru", inn="77",
                           mx_provider="other", вердикт_пробы="принимает всё",
                           в_стоп_листе=None, вердикт_гейта="покупатель")
    assert _по(итог)["proba"] == "warn"
    assert итог["itogo"] == "warn"


def test_myortvyy_adres_krasnyy():
    итог = проверки_письма(email="net@zavod.ru", inn="77", mx_provider="other",
                           вердикт_пробы="нет ящика", в_стоп_листе=None,
                           вердикт_гейта="покупатель")
    assert _по(итог)["proba"] == "bad" and итог["itogo"] == "bad"


def test_stop_list_i_lovushka_krasnye():
    итог = проверки_письма(email="abuse@zavod.ru", inn="77", mx_provider="other",
                           вердикт_пробы="есть", в_стоп_листе="deal_in_progress",
                           вердикт_гейта="покупатель",
                           ловушка=("служебный", "ящик для жалоб"))
    п = _по(итог)
    assert п["stop"] == "bad" and п["lovushki"] == "bad"


def test_svoy_server_predupezhdenie_a_ne_oshibka():
    """Корпоративный шлюз — повод подумать, а не запрет: гейт снят 09.08."""
    итог = проверки_письма(email="snab@zavod.ru", inn="77", mx_provider="other",
                           вердикт_пробы="есть", в_стоп_листе=None,
                           вердикт_гейта="покупатель")
    assert _по(итог)["server"] == "warn" and итог["itogo"] == "warn"


def test_otkaz_probe_ne_horonit():
    """Сервер отказал НАШЕЙ пробе — про адрес не сказано ничего."""
    итог = проверки_письма(email="x@zavod.ru", inn="77", mx_provider="other",
                           вердикт_пробы="отказ пробе", в_стоп_листе=None,
                           вердикт_гейта="покупатель")
    assert _по(итог)["proba"] == "net"


def test_legenda_pokryvaet_vse_znachki():
    коды = {л["код"] for л in ЛЕГЕНДА}
    assert коды == set(ПОРЯДОК)
    итог = проверки_письма(email="a@b.ru", inn=None, mx_provider="yandex",
                           вердикт_пробы="есть", в_стоп_листе=None,
                           вердикт_гейта="покупатель")
    for п in итог["punkty"]:
        assert п["имя"] and п["podpis"] and п["значок"]


def test_neproverennoe_ne_krasnyy_krest():
    """Адрес, который не проверяли, — серый вопрос, а не «нет MX».

    До 11.08 отсутствие сведений и мёртвый домен давали один и тот же красный
    крест: запасной адрес письма, до которого проба не дошла, выглядел как
    адрес с несуществующим доменом. Оператор по такому значку отказался бы от
    живого контакта.
    """
    из_проверки = проверки_письма(
        email="kanc@tog.ru", inn="123", mx_provider=None,
        вердикт_пробы=None, в_стоп_листе=None, вердикт_гейта=None)
    по_коду = {п["код"]: п for п in из_проверки["punkty"]}
    assert по_коду["mx"]["статус"] == "net"
    assert по_коду["server"]["статус"] == "net"
    assert из_проверки["itogo"] == "net"


def test_net_mx_ostayotsya_krasnym():
    """А вот честный вердикт «нет MX» красным быть обязан."""
    из_проверки = проверки_письма(
        email="kto@nesushchestvuet.ru", inn="123", mx_provider=None,
        вердикт_пробы="нет MX", в_стоп_листе=None, вердикт_гейта=None)
    по_коду = {п["код"]: п for п in из_проверки["punkty"]}
    assert по_коду["mx"]["статус"] == "bad"
    assert из_проверки["itogo"] == "bad"


def test_provajder_po_mx():
    """Провайдер запасного адреса берётся из MX, который вернула проба."""
    assert провайдер_по_mx("mx.yandex.net") == "yandex"
    assert провайдер_по_mx("emx.mail.ru") == "mailru"
    assert провайдер_по_mx("aspmx.l.google.com") == "google"
    assert провайдер_по_mx("mail.zavod.ru") == "other"
    assert провайдер_по_mx("") == ""
