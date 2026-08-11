# -*- coding: utf-8 -*-
"""Ручная загрузка партии: разбор обеих форм и честный свод до записи."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sender.import_bazy import применить, разобрать, свод  # noqa: E402

JSONL = "\n".join([
    '{"inn":"5027240707","emails":[{"email":"info@evro.ru","role":"общий"},'
    '{"email":"Sup@evro.ru","person":"Борисов М. А.","role":"продажи"}],'
    '"activity":"мясопереработка","site_title":"Евро","_okved":"10.13"}',
    '{"inn":"7700000000","is_competitor":true,'
    '"emails":[{"email":"kt@konkurent.ru"}]}',
    '{"inn":"7712345678","emails":[],"activity":"без почты"}',
    'это не json',
])

CSV = ("inn;predpriyatie;chelovek;dolzhnost;pochta\n"
       "4221011880;ООО СИБЭЛЕКТРО;Кошилев О. Н.;главный инженер;k@sib.ru\n"
       "4223119624;ООО ЦОФ;Кузнецов Е. Н.;механик;не-адрес\n")


def test_jsonl_razbiraetsya_i_konkurent_ne_gruzitsya():
    контакты, замечания = разобрать(JSONL, "run2.jsonl")
    адреса = {к["email"] for к in контакты}
    assert адреса == {"info@evro.ru", "sup@evro.ru"}, адреса
    # Конкурент — не «пропущенная строка», а осознанно невзятая компания.
    assert any("конкурент" in з for з in замечания), замечания
    по = {к["email"]: к for к in контакты}
    assert по["sup@evro.ru"]["contact_name"] == "Борисов М. А."
    assert по["info@evro.ru"]["company_name"] == "Евро"
    assert по["info@evro.ru"]["okved"] == "10.13"


def test_bitaya_stroka_ne_ronyaet_razbor():
    контакты, замечания = разобрать(JSONL, "run2.jsonl")
    assert контакты, "битая строка утащила за собой весь файл"
    assert any("не разбирается" in з for з in замечания)


def test_csv_s_tochkoy_zapyatoy():
    контакты, замечания = разобрать(CSV, "park.csv")
    assert len(контакты) == 1, контакты
    assert контакты[0]["email"] == "k@sib.ru"
    assert контакты[0]["contact_name"].startswith("Кошилев")
    assert any("узнаны колонки" in з for з in замечания)


def test_csv_bez_pochty_govorit_pryamo():
    контакты, замечания = разобрать("inn;predpriyatie\n7701;ООО Ромашка\n", "x.csv")
    assert контакты == []
    assert any("нет колонки с почтой" in з for з in замечания)


def test_svod_schitaet_dubli():
    контакты, _ = разобрать(JSONL + "\n" + JSONL, "два раза.jsonl")
    итог = свод(контакты, store=None)
    assert итог["vsego_strok"] == 4        # два файла по два адреса
    assert итог["unikalnyh_adresov"] == 2  # дубли сведены
    assert итог["k_zagruzke"] == 2


def test_svod_vidit_stop_list(tmp_path):
    from sender.store import Store

    store = Store(str(tmp_path / "imp.db"))
    store.init_schema()
    ч = "2026-08-11T10:00:00"
    store._conn.execute(  # noqa: SLF001
        "INSERT INTO suppression (scope, value, reason, source, created_at) "
        "VALUES ('email','info@evro.ru','unsub','test',?)", (ч,))
    store._conn.commit()  # noqa: SLF001

    контакты, _ = разобрать(JSONL, "run2.jsonl")
    итог = свод(контакты, store)
    assert итог["v_stop_liste"] == 1, итог
    assert итог["k_zagruzke"] == 1
    assert all(к["email"] != "info@evro.ru" for к in итог["kontakty"])


def test_primenit_pishet_v_gruppu(tmp_path):
    from sender.store import Store

    store = Store(str(tmp_path / "imp2.db"))
    store.init_schema()
    контакты, _ = разобрать(JSONL, "run2.jsonl")
    итог = применить(store, контакты, группа="пищевая-2026-08")
    assert итог["dobavleno"] == 2, итог
    строки = store._conn.execute(  # noqa: SLF001
        "SELECT email, segment, company_name FROM recipients "
        "ORDER BY email").fetchall()
    assert [r[0] for r in строки] == ["info@evro.ru", "sup@evro.ru"]
    assert all(r[1] == "пищевая-2026-08" for r in строки)


def test_ruchka_ne_perekryvaet_staryy_import(tmp_path):
    """Загрузка партии живёт на своём пути.

    Первая редакция встала на /recipients/import — тот же адрес, что у фонового
    импорта CSV из P15. FastAPI отдаёт маршрут зарегистрированному раньше, и
    чужая рабочая ручка молча перестала отвечать. Проверяем, что пути разные и
    оба на месте.
    """
    import re
    import sender.api.app as модуль
    исходник = open(модуль.__file__, encoding="utf-8").read()
    пути = re.findall(r'@app\.post\("(/recipients/[^"]+)"\)', исходник)
    assert "/recipients/import" in пути, пути
    assert "/recipients/zagruzka-partii" in пути, пути
    assert пути.count("/recipients/import") == 1, "путь снова задвоен"
