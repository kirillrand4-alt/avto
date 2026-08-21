# -*- coding: utf-8 -*-
"""На какой АДРЕС приходят отчёты - и есть ли следы postmaster@/abuse@.

Владелец: «postmaster@ что-то такое я делал». Значит такой ящик может
существовать и получать отчёты, просто панель его не читает - в конфиге
его нет. Проверяем по фактам:
  1. на какой адрес падают DMARC-отчёты (они точно доходят - 52 штуки);
  2. встречается ли postmaster@/abuse@ в заголовках входящих писем;
  3. что стоит в DNS: адрес rua= у DMARC-записи каждого домена.
"""
import json
import re
import sqlite3
import subprocess
import sys
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT id, event_type, mailbox_id, COALESCE(detail_json,'') dj "
    "  FROM events WHERE COALESCE(detail_json,'') <> ''").fetchall()

кому, служебные = Counter(), Counter()
for р in ряды:
    try:
        д = json.loads(р["dj"] or "{}")
    except Exception:                                              # noqa: BLE001
        continue
    заг = д.get("headers") or {}
    if not isinstance(заг, dict):
        continue
    плоско = json.dumps(д, ensure_ascii=False)
    for поле in ("To", "Delivered-To", "X-Original-To", "Envelope-To"):
        з = str(заг.get(поле) or "")
        for адрес in re.findall(r"[\w.+-]+@[\w.-]+", з):
            кому[адрес.lower()] += 1
    for адрес in re.findall(r"\b(?:postmaster|abuse|fbl|dmarc)@[\w.-]+", плоско, re.I):
        служебные[адрес.lower()] += 1

print("=== на какие наши адреса приходила входящая ===")
for а, н in кому.most_common(15):
    print(f"  {н:>4}  {а}")
print("\n=== упоминания служебных адресов в письмах ===")
for а, н in служебные.most_common(15):
    print(f"  {н:>4}  {а}")

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
домены = sorted({mb.mailbox_id.split("@")[-1] for mb in cfg.mailboxes()})
print("\n=== DMARC-записи доменов (куда просим слать отчёты) ===")
for д in домены:
    try:
        из = subprocess.run(
            ["nslookup", "-type=TXT", f"_dmarc.{д}"],
            capture_output=True, text=True, timeout=25)
        строки = [s.strip() for s in из.stdout.splitlines()
                  if "v=DMARC" in s or "rua=" in s]
        print(f"  {д}: {' | '.join(строки)[:200] or 'записи не видно'}")
    except Exception as ex:                                        # noqa: BLE001
        print(f"  {д}: ошибка {str(ex)[:60]}")
