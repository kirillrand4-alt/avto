"""Таблица в письме остаётся таблицей, а не столбиком отдельных слов.

26.08 «СМК Альтернатива» прислала техзадание таблицей: давление, расход,
класс чистоты по каждой установке. В карточке лида это читалось как
«No», «Описание», «Давление,», «МПа» — по слову на строку: внутри ячеек
почтовый редактор кладёт <p>, а это блочный тег.
"""

import os
import sys

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.pismo_v_tekst import tablicy_v_stroki, v_tekst  # noqa: E402


def test_stroka_tablicy_odnoy_strokoy():
    h = ("<table><tr><td><p>No</p></td><td><p>Описание</p></td>"
         "<td><p>Давление,<br>МПа</p></td></tr></table>")
    из = v_tekst(h)
    assert из == "No | Описание | Давление, МПа"


def test_dve_stroki_ostayutsya_dvumya():
    h = ("<table><tr><td>No</td><td>Описание</td></tr>"
         "<tr><td>1</td><td>Камера для эмали</td></tr></table>")
    строки = [с for с in v_tekst(h).splitlines() if с.strip()]
    assert строки == ["No | Описание", "1 | Камера для эмали"]


def test_odna_yacheyka_bez_razdelitelya():
    """Таблицами верстают и обычные абзацы — « | » там был бы мусором."""
    h = "<table><tr><td><p>Просто абзац письма</p></td></tr></table>"
    assert v_tekst(h) == "Просто абзац письма"


def test_pustye_hvostovye_yacheyki_ne_dayut_palok():
    h = "<table><tr><td>Итого</td><td>8</td><td></td><td></td></tr></table>"
    assert v_tekst(h) == "Итого | 8"


def test_tekst_vokrug_tablicy_na_meste():
    h = ("<div>Добрый день.</div><table><tr><td>А</td><td>Б</td></tr></table>"
         "<div>Готовы выслушать.</div>")
    строки = [с for с in v_tekst(h).splitlines() if с.strip()]
    assert строки == ["Добрый день.", "А | Б", "Готовы выслушать."]


def test_br_vnutri_yacheyki_ne_rvyot_stroku():
    h = "<table><tr><td>Расход,<br/>нм^3 /мин</td><td>0.3~0.4</td></tr></table>"
    assert v_tekst(h) == "Расход, нм^3 /мин | 0.3~0.4"


def test_bez_tablicy_nichego_ne_menyaetsya():
    assert tablicy_v_stroki("<p>обычное письмо</p>") == "<p>обычное письмо</p>"
    assert v_tekst("Просто текст без разметки") == "Просто текст без разметки"


def test_vlozhennaya_tablica_ne_ronyaet():
    """Верстальщики писем вкладывают таблицы друг в друга — не падаем."""
    h = ("<table><tr><td><table><tr><td>вложено</td></tr></table></td>"
         "<td>рядом</td></tr></table>")
    из = v_tekst(h)
    assert "вложено" in из and "рядом" in из


# --- какую часть письма показывать ------------------------------------------ #

from sender.pismo_v_tekst import est_tablica, luchshee_telo  # noqa: E402

# Как Outlook кладёт таблицу в текстовую часть: ячейки по строкам, между
# ними табуляция и пустые строки. Читать это невозможно.
PLAIN_OUTLOOK = ("Основные требования:\n\nNo\n\n\t\n\nОписание\n\n\t\n\n"
                 "Давление,\n\nМПа\n\n")
HTML_OUTLOOK = ("<div>Основные требования:</div><table>"
                "<tr><td><p>No</p></td><td><p>Описание</p></td>"
                "<td><p>Давление,<br>МПа</p></td></tr></table>")


def test_est_tablica():
    assert est_tablica(HTML_OUTLOOK) is True
    assert est_tablica("<div>просто письмо</div>") is False
    assert est_tablica("") is False


def test_pri_tablice_berem_html():
    из = luchshee_telo(PLAIN_OUTLOOK, HTML_OUTLOOK)
    assert "No | Описание | Давление, МПа" in из
    assert "\t" not in из


def test_bez_tablicy_berem_tekstovuyu_chast():
    """Обычное письмо: текстовая часть — это то, что писал человек."""
    из = luchshee_telo("Добрый день. Не актуально.",
                       "<div>Добрый день. Не актуально.</div>")
    assert из == "Добрый день. Не актуально."


def test_tekstovoy_chasti_net_berem_html():
    из = luchshee_telo("", "<div>только разметка</div>")
    assert из == "только разметка"


def test_obe_chasti_pusty():
    assert luchshee_telo("", "") == ""
