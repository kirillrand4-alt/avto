# -*- coding: utf-8 -*-
"""Ящик против письма: где подпись ушла от чужого направления.

ПОВОД. Владелец показал письмо ГАСТРОФАБРИКЕ от 20.08: тело мейеровское
(«представляю компанию «Руспром Meyer»», рентген-инспекция, оптическая
сортировка), а подпись и домен - КЦ (v.melnikov@kompressor-air-trade.ru,
«Компрессор Центр»). Его слова: «когда вручную делал копии и отправлял,
отправил не проверив направление».

ЧТО СВЕРЯЕМ. Три показания на каждое ОТПРАВЛЕННОЕ письмо:
  1. направление ЯЩИКА - sender.yaml, mailboxes[].division;
  2. направление ПИСЬМА - panel_json.letter_division карточки подтверждения
     (ровно то поле, которое читает гейт sender.division_block);
  3. ГОЛОС ТЕЛА - чем письмо представляется получателю: зачин «Руспром
     Meyer»/рентген-инспекция против «Компрессор Центр»/сжатый воздух.
Голос тела важнее всего: гейт слеп, когда карточки нет вовсе (копии), а
получатель видит именно тело.
"""
import json
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
ящик_напр = {mb.mailbox_id: (mb.division or "") for mb in cfg.mailboxes()}
print(f"ящиков в конфиге: {len(ящик_напр)}; "
      f"без направления: {sum(1 for v in ящик_напр.values() if not v)}")

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT m.id mid, m.mailbox_id, m.campaign_id, m.subject, "
    "       substr(m.sent_at,1,16) когда, COALESCE(m.body_rendered,'') тело, "
    "       r.email, r.company_name, r.inn, "
    "       cr.id rid, COALESCE(cr.panel_json,'') pj "
    "  FROM messages m "
    "  LEFT JOIN recipients r ON r.id=m.recipient_id "
    "  LEFT JOIN confirm_reviews cr ON cr.message_id=m.id "
    " WHERE m.status='sent' ORDER BY m.sent_at"
).fetchall()
print(f"отправленных писем всего: {len(ряды)}")

_МЕЙЕР = re.compile(r"Руспром\s*Meyer|Руспром\s*Мейер|рентген-инспекц|"
                    r"фотосепаратор|оптическ\w+ сортировк|посторонн\w+ включен",
                    re.I)
_КЦ = re.compile(r"Компрессор\s*Центр|компрессорн\w+ парк|сжат\w+ воздух|"
                 r"пневмоаудит|генерац\w+ азота", re.I)


def голос(тело: str) -> str:
    """Направление ПО ТЕЛУ, по зачину: первые 900 знаков - это самопред-
    ставление и суть. Подпись в конце сюда не попадает намеренно: она
    строится по ящику и показала бы направление ящика, а не письма."""
    зачин = тело[:900]
    м, к = bool(_МЕЙЕР.search(зачин)), bool(_КЦ.search(зачин))
    return "meyer" if м and not к else "kc" if к and not м else ""


счёт, беды, без_карточки = {}, [], 0
for р in ряды:
    ян = ящик_напр.get(str(р["mailbox_id"] or ""), "")
    try:
        п = json.loads(р["pj"] or "{}")
    except Exception:                                              # noqa: BLE001
        п = {}
    пд = str(п.get("letter_division")
             or ((п.get("letter") or {}).get("division")) or "").lower()
    г = голос(str(р["тело"] or ""))
    if not р["rid"]:
        без_карточки += 1
    к = f"ящик={ян or '?'} письмо={пд or '-'} голос={г or '-'}"
    счёт[к] = счёт.get(к, 0) + 1
    if ян and ((пд and пд != ян) or (г and г != ян)):
        беды.append((р["когда"], р["mid"], р["mailbox_id"], р["email"],
                     р["company_name"], ян, пд, г, р["rid"], р["subject"]))

print(f"писем без карточки подтверждения: {без_карточки}")
print("\nраскладка (ящик / письмо / голос тела):")
for к, н in sorted(счёт.items(), key=lambda x: -x[1]):
    print(f"  {н:>4}  {к}")

print(f"\nПИСЕМ С ЧУЖИМ ЯЩИКОМ: {len(беды)}")
по_дням = {}
for б in беды:
    по_дням[str(б[0])[:10]] = по_дням.get(str(б[0])[:10], 0) + 1
print("по дням:", dict(sorted(по_дням.items())))
print("\nпервые 25:")
for б in беды[:25]:
    print(f"  {б[0]} msg{б[1]} {б[2]}")
    print(f"       -> {б[3]} | {str(б[4])[:32]} | ИНН {б[5] if False else ''}"
          f"ящик={б[5]} письмо={б[6] or '-'} голос={б[7] or '-'} "
          f"карточка={'есть' if б[8] else 'НЕТ'}")
    print(f"       {str(б[9])[:70]}")
