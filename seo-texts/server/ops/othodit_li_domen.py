# -*- coding: utf-8 -*-
"""Отходит ли домен, которого глушат: смотрим по своей истории.

Вопрос владельца прямой: тот, кого глушат как спам, отойдёт? Отвечать на
общих соображениях тут нельзя - у нас есть собственные замеры. Три вещи
показывают ответ:
  1. отказы и отправка ПО ДНЯМ и по направлениям - если после дня с
     отказами следующий день чистый, домен отходит;
  2. глухая ли блокировка - если в тот же час часть писем всё же уходит,
     это не бан домена, а оценка каждого письма;
  3. уходило ли что-нибудь ПОСЛЕ последнего отказа.
"""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row


def напр(камп):
    return "КЦ" if int(камп or 0) in (9, 10) else "Meyer"


ушло = c.execute(
    "SELECT campaign_id, substr(COALESCE(sent_at,updated_at),1,10) день, "
    "       substr(COALESCE(sent_at,updated_at),1,16) когда "
    "  FROM messages WHERE status='sent'").fetchall()
отказ = c.execute(
    "SELECT campaign_id, substr(updated_at,1,10) день, "
    "       substr(updated_at,1,16) когда, mailbox_id "
    "  FROM messages WHERE COALESCE(last_error,'') LIKE '%suspicion of SPAM%'"
).fetchall()

print("=== 1. по дням и направлениям ===")
print(f"{'день':<12} {'КЦ ушло':>8} {'КЦ отк':>7} {'Meyer ушло':>11} "
      f"{'Meyer отк':>10} {'доля Meyer':>11}")
дни = sorted({str(р["день"]) for р in ушло} | {str(р["день"]) for р in отказ})
for д in дни[-8:]:
    ку = sum(1 for р in ушло if str(р["день"]) == д and напр(р["campaign_id"]) == "КЦ")
    ко = sum(1 for р in отказ if str(р["день"]) == д and напр(р["campaign_id"]) == "КЦ")
    му = sum(1 for р in ушло if str(р["день"]) == д and напр(р["campaign_id"]) == "Meyer")
    мо = sum(1 for р in отказ if str(р["день"]) == д and напр(р["campaign_id"]) == "Meyer")
    доля = (100.0 * мо / (му + мо)) if (му + мо) else 0
    print(f"{д:<12} {ку:>8} {ко:>7} {му:>11} {мо:>10} {доля:>10.1f}%")

print("\n=== 2. глухая ли блокировка: сегодня по минутам ===")
события = ([("ушло", str(р["когда"])) for р in ушло
            if str(р["день"]) == "2026-08-21" and напр(р["campaign_id"]) == "Meyer"]
           + [("ОТКАЗ", str(р["когда"])) for р in отказ
              if str(р["день"]) == "2026-08-21"])
события.sort(key=lambda x: x[1])
по_минутам = {}
for что, когда in события:
    по_минутам.setdefault(когда, Counter())[что] += 1
for когда in sorted(по_минутам)[-16:]:
    с = по_минутам[когда]
    print(f"  {когда}  ушло {с['ушло']:>3}   отказов {с['ОТКАЗ']:>3}")

print("\n=== 3. после последнего отказа ===")
if события:
    последний_отказ = max((к for ч, к in события if ч == "ОТКАЗ"), default=None)
    после = [к for ч, к in события if ч == "ушло" and последний_отказ
             and к > последний_отказ]
    print(f"последний отказ: {последний_отказ}")
    print(f"писем ушло ПОСЛЕ него: {len(после)}"
          + (f", первое в {после[0]}" if после else ""))
