# -*- coding: utf-8 -*-
"""Задача 57: углы по ротации, роль -> угол, тон по размеру, ОКВЭД -> боль,
подписант кампании, best_email по приоритету ролей."""

import os
import sys

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.ai_letter import (  # noqa: E402
    NEWS_MECHANICS, ROLE_ANGLES, SIZE_TONE, _recipient_block, company_size,
    equipment_pitch, gen_prompt,
)


# --------------------------------------------------------------- §7в: боли --- #
def test_pain_exact_code_beats_parent():
    # 10.6 (мукомольная) точнее, чем 10 (пищёвка) — для meyer оба заданы
    assert equipment_pitch("10.6", "meyer") != equipment_pitch("10", "meyer")
    assert "зерно" in equipment_pitch("10.6", "meyer")


def test_pain_falls_back_to_parent_and_default():
    # 25.62 в таблице нет — берётся раздел 25
    assert equipment_pitch("25.62", "kc") == equipment_pitch("25", "kc")
    # неизвестный раздел — общий дефолт направления, не пустота
    assert equipment_pitch("99.99", "kc") != ""


def test_pains_differ_between_industries():
    codes = ["10", "20", "24", "25", "37", "41", "45", "72", "77", "86"]
    pains = [equipment_pitch(c, "kc") for c in codes]
    assert len(set(pains)) == len(pains), "боли отраслей не должны совпадать"


# ------------------------------------------------------ §7а/7б: роль и тон --- #
def test_recipient_block_carries_role_and_size():
    rec = {"company_name": "ООО Завод", "okved": "25.62", "mode": "GENERIC",
           "extra": {"role": "снабжение/закупки", "revenue": "18600000000"}}
    block = _recipient_block(0, rec, "kc")
    assert "угол снабженца" in block
    assert SIZE_TONE["крупный"] in block


def test_company_size_thresholds():
    assert company_size("50000000") == "микро"
    assert company_size("500000000") == "малый"
    assert company_size("1500000000") == "средний"
    assert company_size("18600000000") == "крупный"
    assert company_size("") == ""       # нет выручки — нет и тона
    assert company_size("мусор") == ""


def test_unknown_role_adds_nothing():
    rec = {"company_name": "ООО", "okved": "25", "mode": "GENERIC",
           "extra": {"role": "космонавт"}}
    assert "РОЛЬ АДРЕСАТА" not in _recipient_block(0, rec, "kc")


# ------------------------------------------------------- §5б: ротация углов --- #
def _news_rec(i):
    return {"company_name": f"К{i}", "okved": "25", "mode": "NEWS",
            "extra": {"news_object": "новый цех", "city": "Тверь"}}


def test_adjacent_letters_get_different_mechanics():
    b0 = _recipient_block(0, _news_rec(0), "kc")
    b1 = _recipient_block(1, _news_rec(1), "kc")
    m0 = [ln for ln in b0.splitlines() if ln.startswith("МЕХАНИКА")][0]
    m1 = [ln for ln in b1.splitlines() if ln.startswith("МЕХАНИКА")][0]
    assert m0 != m1


def test_angle_rotation_continues_across_batches():
    # партия 2: angle_base=4 продолжает круг, а не начинает с первой механики
    b = _recipient_block(0, _news_rec(0), "kc", angle_base=4)
    assert NEWS_MECHANICS[4].split(":")[0] in b


def test_no_angle_exceeds_quarter_of_batch():
    # 12 писем, 10 механик: максимум 2 на угол (17%) — в лимите 25%
    from collections import Counter
    cnt = Counter()
    for i in range(12):
        block = _recipient_block(i, _news_rec(i), "kc")
        mech = [ln for ln in block.splitlines() if ln.startswith("МЕХАНИКА")][0]
        cnt[mech] += 1
    assert max(cnt.values()) <= max(1, round(12 * 0.25))


def test_gen_prompt_orders_assigned_mechanic():
    p = gen_prompt([_news_rec(0)], {"division": "kc"}, "kc")
    assert "НАЗНАЧЕНА" in p and "не подменяй" in p


# ------------------------------------------------- §8: подписант кампании --- #
def test_signature_uses_campaign_manager():
    from types import SimpleNamespace
    from sender.sender import Sender
    from sender.dtos import RenderedMessage

    class _Cfg:
        def get(self, k, d=None):
            return d

        def legal(self):
            return SimpleNamespace(inn="1655249223")

    s = Sender.__new__(Sender)          # без полного конструктора
    s.config = _Cfg()
    s._mailbox_cfg = lambda mid: SimpleNamespace(
        from_name="Владислав Мельников, Компрессор Центр")
    camp = SimpleNamespace(legal_inn="1655249223",
                           config={"manager_name": "Пётр Смирнов",
                                   "manager_role": "Руководитель направления"})
    out = s._apply_signature(RenderedMessage(subject="т", body="Тело.\n"),
                             "box1", camp)
    assert "Пётр Смирнов" in out.body
    assert "Руководитель направления," in out.body
    assert "Владислав" not in out.body
    # без полей кампании — как раньше: имя из ящика, роль по умолчанию
    camp2 = SimpleNamespace(legal_inn="", config={})
    out2 = s._apply_signature(RenderedMessage(subject="т", body="Тело.\n"),
                              "box1", camp2)
    assert "Владислав Мельников" in out2.body
    assert "Менеджер по продажам," in out2.body


# ------------------------------------- best_email по приоритету ролей (57) --- #
def test_best_email_role_priority():
    sys.path.insert(0, os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "server")))
    from enrich_contacts import _best_by_role
    emails = [{"email": "info@x.ru", "role": "общий"},
              {"email": "sales@x.ru", "role": "продажи"},
              {"email": "zakupki@x.ru", "role": "снабжение/закупки"}]
    # модель предложила info@ — код выбирает закупки
    assert _best_by_role(emails, "info@x.ru") == "zakupki@x.ru"
    # ничья внутри роли решается подсказкой модели
    emails2 = [{"email": "a@x.ru", "role": "общий"},
               {"email": "b@x.ru", "role": "общий"}]
    assert _best_by_role(emails2, "b@x.ru") == "b@x.ru"
    assert _best_by_role([], "z@x.ru") == "z@x.ru"


# --------------------------------------- #68: идея захода в блоке (GENERIC) --- #
def test_idea_rendered_only_when_present():
    rec = {"company_name": "ООО", "okved": "25", "mode": "GENERIC",
           "extra": {"idea": "спросить, чем закрывают пики потребления воздуха"}}
    assert "ИДЕЯ ЗАХОДА" in _recipient_block(0, rec, "kc")
    rec2 = {"company_name": "ООО", "okved": "25", "mode": "GENERIC", "extra": {}}
    assert "ИДЕЯ ЗАХОДА" not in _recipient_block(0, rec2, "kc")


def test_ideas_skip_news_and_survive_missing_provider():
    """NEWS-письма идею не получают; без провайдера (как в тестах) квота
    молча работает дальше."""
    from sender.ai_quota import AiQuota

    class _Cfg:
        def get(self, k, d=None):
            return d

    q = AiQuota.__new__(AiQuota)
    q._config = _Cfg()
    # пустые линзы: провайдер в тесте НЕ дёргается (иначе тест ходит в сеть
    # с ретраями и висит минутами), а ветка «NEWS пропускаем» отрабатывает
    q._IDEA_LENSES = {}
    reqs = [
        {"company_name": "А", "okved": "25",
         "extra": {"news_object": "завод", "city": "Тверь"}},
        {"company_name": "Б", "okved": "10", "extra": {}},
    ]
    q._add_ideas_generic(reqs)
    assert "idea" not in (reqs[0]["extra"] or {})
    assert "idea" not in (reqs[1]["extra"] or {})
