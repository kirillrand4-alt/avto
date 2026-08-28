# -*- coding: utf-8 -*-
"""Третья линза — покупатель: может ли компания вообще у нас купить.

Владелец 28.08: «поставь судью в генерацию перед очередью». Судья по 971
письму партии вторых адресов нашёл 19% таких, каких технолог и скептик не
видят: они проверяют, правду ли письмо говорит о ТЕХНОЛОГИИ, а врал сам
выбор адресата — письмо про компрессоры производителю промышленных газов,
диагностической клинике, ИТ-компании.
"""
import sender.ai_letter as AL
from sender.ai_letter import НЕ_ПОКУПАТЕЛЬ, teh_lens_prompt


def _ген(ответы):
    """Генератор с подставным _ask: отдаёт заготовленные вердикты по тегу."""
    спрошено = []

    class Ген(AL.AiLetterGen):
        def _ask(self, prompt, tag, **kw):
            спрошено.append((tag, prompt))
            for ключ, ответ in ответы.items():
                if tag.startswith(ключ):
                    return ответ
            return {"verdicts": [], "letters": []}

    g = Ген(lambda p: "", facts={}, default_division="kc")
    return g, спрошено


def test_promt_nesyot_tretiy_vzglyad():
    для = [(0, "Праксэа", "промышленные газы", "20.11", "т", "б", "")]
    for div in ("kc", "meyer_rentgen"):
        п = teh_lens_prompt(для, "три", div)
        assert "ВЗГЛЯД ТРЕТИЙ" in п
        assert "ПОКУПАТЕЛЬ" in п
        assert "худший из трёх" in п


def test_u_oboih_napravleniy_svoy_pokupatel():
    kc = teh_lens_prompt([(0, "З", "", "25.11", "т", "б", "")], "три", "kc")
    me = teh_lens_prompt([(0, "З", "", "10.61", "т", "б", "")], "три",
                         "meyer_rentgen")
    assert "компрессорного" in kc and "фотосепараторы" in me
    # мейеровский покупатель не требует сжатого воздуха
    assert "воздухоразделительными" in kc
    assert "машинного зрения" in me


def test_stariy_klyuch_obe_zhiv():
    """Ключ 'обе' остаётся: на него смотрят прежние тесты и калибровки."""
    п = teh_lens_prompt([(0, "З", "", "25.11", "т", "б", "")], "обе", "kc")
    assert "ВЗГЛЯД ВТОРОЙ" in п and "ВЗГЛЯД ТРЕТИЙ" not in п


def test_ne_pokupatel_brakuetsya_bez_pochinki():
    """Компанию правкой текста в покупателя не превратить — чинить нечего."""
    претензия = НЕ_ПОКУПАТЕЛЬ + ": сами производят промышленные газы"
    g, спрошено = _ген({"tehтри": {"verdicts": [
        {"idx": 0, "verdict": "ошибка", "chto_ne_tak": претензия}]}})
    letters = {0: {"subject": "т", "body": "б"}}
    recipients = {0: {"company_name": "Праксэа", "activity": "", "okved": "20.11",
                      "mode": "GENERIC"}}
    res = AL.GenResult() if hasattr(AL, "GenResult") else None
    res = res or type("R", (), {"rejected": {}, "drafts": {}, "calls": 0})()
    res.rejected, res.drafts, res.calls = {}, {}, 0
    rounds = {0: []}
    g._teh_lens_stage(letters, recipients, {0: "kc"}, res, rounds)
    assert 0 not in letters, "безнадёжное письмо должно уйти из выдачи"
    assert 0 in res.rejected
    assert НЕ_ПОКУПАТЕЛЬ in res.rejected[0][0]
    assert 0 in res.drafts, "черновик сохраняем для разбора"
    теги = [t for t, _ in спрошено]
    assert not any(t.startswith("tehfx") for t in теги), \
        "починку безнадёжного письма не запускаем"


def test_obychnaya_oshibka_idyot_v_pochinku():
    """Претензия без метки — правимая: чинилку зовём, как и раньше."""
    зовы = {"tehтри": {"verdicts": [
        {"idx": 0, "verdict": "ошибка",
         "chto_ne_tak": "в гальванике воздухом не сушат"}]}}
    g, спрошено = _ген(зовы)
    letters = {0: {"subject": "т", "body": "б"}}
    recipients = {0: {"company_name": "Завод", "activity": "", "okved": "25.61",
                      "mode": "GENERIC"}}
    res = type("R", (), {})()
    res.rejected, res.drafts, res.calls = {}, {}, 0
    g._teh_lens_stage(letters, recipients, {0: "kc"}, res, {0: []})
    теги = [t for t, _ in спрошено]
    assert any(t.startswith("tehfx") for t in теги), \
        "правимое письмо должно попасть в починку"


def test_verno_nichego_ne_trogaet():
    g, спрошено = _ген({"tehтри": {"verdicts": [
        {"idx": 0, "verdict": "верно", "chto_ne_tak": ""}]}})
    letters = {0: {"subject": "т", "body": "б"}}
    recipients = {0: {"company_name": "Завод", "activity": "", "okved": "25.61",
                      "mode": "GENERIC"}}
    res = type("R", (), {})()
    res.rejected, res.drafts, res.calls = {}, {}, 0
    g._teh_lens_stage(letters, recipients, {0: "kc"}, res, {0: []})
    assert 0 in letters and not res.rejected
