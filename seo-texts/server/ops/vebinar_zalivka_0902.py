# -*- coding: utf-8 -*-
"""Заливка базы вебинара: кампания, группа vebinar-2609, 175 писем
в очередь подтверждения.

Ничего не отправляет и ничего не одобряет: письма ложатся в confirm_reviews
со статусом pending, решение остаётся за владельцем.

argv: проба | делать
"""
import io
import json
import os
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store, CampaignIn, RecipientIn  # noqa: E402

РЕЖИМ = sys.argv[1] if len(sys.argv) > 1 else "проба"
ДЕЛАТЬ = РЕЖИМ == "делать"
ГРУППА = "vebinar-2609"
ИМЯ_КАМПАНИИ = "Вебинар — Meyer"
ИСТОЧНИК = "вебинар 26.09"

БАЗА = os.path.dirname(os.path.abspath(__file__))
письма = []
for i in range(3):
    п = os.path.join(БАЗА, "vebinar_pisma_%d.json" % i)
    письма.extend(json.loads(io.open(п, encoding="utf-8").read()))
print("писем на входе: %d, режим: %s" % (len(письма), РЕЖИМ))

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

# --- кампания ---
кид = None
for к in store.list_campaigns():
    if getattr(к, "name", None) == ИМЯ_КАМПАНИИ:
        кид = к.id
        print("кампания уже есть: id=%s" % кид)
        break
if кид is None:
    if ДЕЛАТЬ:
        кид = store.create_campaign(CampaignIn(
            name=ИМЯ_КАМПАНИИ,
            legal_entity="ООО «Руспром»",
            legal_inn="2221239841",
            provider_pool=None,
            config={"segment": "meyer", "division": "meyer",
                    "letter_mode": "shablon", "ai_mode": "off",
                    "gruppa": ГРУППА, "istochnik": ИСТОЧНИК,
                    "opisanie": "участники вебинара «ИИ в контроле качества»"}))
        print("кампания создана: id=%s" % кид)
    else:
        print("кампания будет создана: %s (дивизион meyer)" % ИМЯ_КАМПАНИИ)

ст = {"новых": 0, "было": 0, "в_очередь": 0, "дубль": 0, "стоп": 0, "ошибка": 0}
примеры = []
for п in письма:
    почта = п["email"]
    домен = почта.split("@")[-1]
    сущ = store.find_recipient_by_email(почта)
    доп = {}
    if сущ:
        ст["было"] += 1
        try:
            доп = json.loads(сущ.get("extra_json") or "{}")
        except Exception:
            доп = {}
    else:
        ст["новых"] += 1
    группы = list(доп.get("gruppy") or [])
    if ГРУППА not in группы:
        группы.append(ГРУППА)
    доп["gruppy"] = группы
    доп["volna"] = ГРУППА
    доп["rol"] = "участник вебинара"
    доп["zachem"] = "тёплая база: сам зарегистрировался на наш вебинар"
    доп["vebinar_blocki"] = п["блоки"]
    if п.get("ящик"):
        доп["yashchik"] = п["ящик"]

    if not ДЕЛАТЬ:
        if len(примеры) < 3:
            примеры.append("%s -> группы %s" % (почта, группы))
        continue

    рид = store.upsert_recipient(RecipientIn(
        email=почта, domain=домен, inn=п.get("inn"),
        company_name=(п.get("компания") or None),
        okved=(сущ or {}).get("okved"),
        segment=((сущ or {}).get("segment") or "meyer"),
        bitrix_id=(сущ or {}).get("bitrix_id"),
        contact_name=(п.get("обращение") or (сущ or {}).get("contact_name")),
        source=ИСТОЧНИК,
        priority_max=(сущ or {}).get("priority_max"),
        priority_total=(сущ or {}).get("priority_total"),
        pxr=(сущ or {}).get("pxr"),
        region=(сущ or {}).get("region"),
        tz=(сущ or {}).get("tz"),
        extra=доп))

    панель = {
        "actions": {"confirm_hold": False},
        "ai": False,
        "letter_division": "meyer",
        "letter_division_reason": "кампания вебинара, дивизион meyer",
        "company": {"name": п.get("компания") or "", "inn": п.get("inn") or ""},
        "contact": {"name": п.get("обращение") or "", "email": почта},
        "vebinar": {"gruppa": ГРУППА, "blocki": п["блоки"],
                    "stroka": п["строка"], "yashchik": п.get("ящик")},
    }
    try:
        рев, новый = store.confirm_submit(
            email=почта, subject=п["тема"], body=п["тело"],
            inn=п.get("inn"), campaign_id=кид, recipient_id=рид,
            panel=панель, status="pending")
        если = store.confirm_get(рев) or {}
        if если.get("status") == "skipped":
            ст["стоп"] += 1
        elif новый:
            ст["в_очередь"] += 1
        else:
            ст["дубль"] += 1
    except Exception as ex:
        ст["ошибка"] += 1
        if ст["ошибка"] <= 3:
            print("  ошибка на %s: %s" % (почта, str(ex)[:140]))

if not ДЕЛАТЬ:
    print("\n=== ЧТО БУДЕТ СДЕЛАНО ===")
    print("  получателей новых: %d, уже есть в базе: %d" % (ст["новых"], ст["было"]))
    for x in примеры:
        print("  " + x)
    print("  писем в очередь подтверждения: %d" % len(письма))
    print("  ничего не изменено (режим пробы)")
else:
    print("\n=== СДЕЛАНО ===")
    print("  кампания: id=%s «%s»" % (кид, ИМЯ_КАМПАНИИ))
    print("  получателей новых %d, обновлено %d" % (ст["новых"], ст["было"]))
    print("  в очередь подтверждения: %d" % ст["в_очередь"])
    print("  повторов (уже были): %d" % ст["дубль"])
    print("  срезано стоп-листом на входе: %d" % ст["стоп"])
    print("  ошибок: %d" % ст["ошибка"])
    сч = store.confirm_counts()
    print("  очередь подтверждений теперь: %s" % json.dumps(сч, ensure_ascii=False)[:200])
