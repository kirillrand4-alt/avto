# -*- coding: utf-8 -*-
"""Задержанные заслоном recent_contact карточки кампании 23 — по правилу владельца 11.11: мешает только письмо КЦ на
ТОТ ЖЕ адрес < 15 дней; письма Meyer не мешают. Проходящие — ручная отправка через confirm.approve(force=True)
(автоотправка такой адрес не возьмёт: она снимает любой ранее писанный адрес). Пауза 20 с между письмами.
Гейт направлений (компания за Meyer) не трогаем — решает владелец.   razobrat_zaderzhannye_23.py [--primenit]"""
import io, os, re, sqlite3, sys, time
from collections import Counter
from datetime import datetime, timezone
ПРИМ = "--primenit" in sys.argv
if "--zapusk" in sys.argv:
    import subprocess
    л = io.open(r"C:\sender\_ops\razobrat-zaderzhannye-23.log", "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__), "--primenit"], cwd=r"C:\sender", stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    time.sleep(5); print("запущен, pid %d" % п.pid); sys.exit(0)
if ПРИМ:
    for с in io.open(r"C:\sender\panel.env", encoding="utf-8-sig"):
        if "=" in с and not с.lstrip().startswith("#"):
            к, v = с.split("=", 1); os.environ.setdefault(к.strip(), v.strip().strip('"'))
sys.path.insert(0, r"C:\sender")
from sender.config import Config
from sender.store import Store
from sender.wiring import build_deps
cfg = Config.load(r"C:\sender\sender.yaml"); st = Store(r"C:\sender\sender.db")
cs = build_deps(cfg, st, dry_run=not ПРИМ).confirm
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
now = datetime.now(timezone.utc); сч = Counter()
for rid, inn, em in c.execute("SELECT id, inn, lower(email) FROM confirm_reviews WHERE campaign_id=23 AND status='pending'").fetchall():
    блок = cs._guard(inn=inn, email=em or "")
    if not блок or not str(блок).startswith("recent_contact"): сч["другое: " + str(блок)[:30]] += 1; continue
    посл = c.execute("SELECT m.mailbox_id, m.sent_at FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE lower(r.email)=? AND m.status='sent' "
                     "ORDER BY m.sent_at DESC LIMIT 1", (em,)).fetchone()
    if not посл: сч["контакт не найден в messages"] += 1; continue
    мейер = bool(re.search(r"sort|rentgen|inspection|optic", посл[0] or ""))
    дней = (now - datetime.fromisoformat(посл[1][:19]).replace(tzinfo=timezone.utc)).days
    if not мейер and дней < 15: сч["КЦ на этот адрес < 15 дн — не шлём"] += 1; continue
    к = "проходит: писал Meyer" if мейер else "проходит: КЦ %d+ дн назад" % 15
    сч[к] += 1
    if ПРИМ:
        try:
            р = cs.approve(rid, operator="владелец 16.11: по правилам (КЦ тот же адрес <15д / Meyer не мешает)", force=True)
            сч["отправлено" if getattr(р, "ok", р) else "не ушло"] += 1
        except Exception as ex: сч["ошибка: " + str(ex)[:50]] += 1  # noqa: BLE001
        time.sleep(20)
print("ОТПРАВКА" if ПРИМ else "сухой", dict(сч))
