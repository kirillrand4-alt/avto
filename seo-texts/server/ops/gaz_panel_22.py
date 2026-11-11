# -*- coding: utf-8 -*-
"""Полная информационная панель для карточек кампании 22 «КЦ газ 11.11» (владелец 11.11: «никакой информации нет
о компании, как было во всех компаниях до этого»). Собираем штатно — sender.infopanel.build_panel с теми же
источниками, что ai_quota (enrich-лид, карточка обзвона, превью подписи для комплаенса), и дополняем данными ЦА
там, где в обогащении пусто: продукция, оборудование, отрасль, газ, почему подходит, фраза письма.
Наши ключи (letter_division, mailbox_id, vruchnuyu, adres_za_drugim_inn) сохраняются поверх.

    gaz_panel_22.py            — сухой прогон на 30 карточках: что получится, сколько стоп-флагов
    gaz_panel_22.py --zapusk   — фоном по всем pending, лог _ops\\gaz-panel-22.log, резюмируемо"""
import csv, io, json, os, re, subprocess, sys, time
from collections import Counter
ОПС = r"C:\sender\_ops"
if "--zapusk" in sys.argv:
    л = io.open(os.path.join(ОПС, "gaz-panel-22.log"), "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__), "--primenit"], cwd=r"C:\sender", stdout=л, stderr=л,
                         creationflags=0x00000008 | 0x00000200)
    time.sleep(5); print("запущен, pid %d" % п.pid); sys.exit(0)
sys.path.insert(0, r"C:\sender"); sys.path.insert(0, r"C:\sender\server")
from sender.config import Config               # noqa: E402
from sender.store import Store                 # noqa: E402
from sender.ai_quota import build_ai_quota     # noqa: E402
from sender.infopanel import build_panel, load_enrich_lead   # noqa: E402
csv.field_size_limit(10 ** 9)
ПРИМЕНИТЬ = "--primenit" in sys.argv
ДРОП = r"C:\seostat\drop\drop-storage"
def читать(имя):
    return list(csv.DictReader(io.open(os.path.join(ДРОП, имя), encoding="utf-8-sig", errors="replace"), delimiter=";"))
def цифры(x): return re.sub(r"\D", "", str(x or ""))
база = {}
for р in читать("CA-ENGER-ZALIVKA.csv") + читать("CA-ENGER-ZALIVKA-kompanii.csv"):
    и = цифры(р.get("ИНН"))
    if и and (и not in база or not (база[и].get("Продукция") or "").strip()):
        база[и] = р
сайт = {цифры(р.get("ИНН")): р for р in читать("CA-ENGER-BAZA-kompanii.csv")}
суд = {}
for с in io.open(os.path.join(ОПС, "gaz-kc-sud.jsonl"), encoding="utf-8"):
    try: з = json.loads(с); суд[з["inn"]] = з
    except ValueError: pass
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
к = store._conn
q = build_ai_quota(store, cfg)
подпись = q._signature_preview("kc")
ряды = к.execute("SELECT id, inn, email, subject, COALESCE(edited_body, body), panel_json FROM confirm_reviews "
                 "WHERE campaign_id=22 AND status='pending' ORDER BY id").fetchall()
if not ПРИМЕНИТЬ:
    ряды = ряды[:30]
сч = Counter(); флаги = Counter(); пример = None
for кид, inn, em, тема, тело, pj in ряды:
    стар = json.loads(pj or "{}")
    if стар.get("company_full") is not None and ПРИМЕНИТЬ:
        сч["уже полная"] += 1; continue
    и = цифры(inn); р = база.get(и, {}); с = сайт.get(и, {}); з = суд.get(и, {})
    try:
        ctx = load_enrich_lead(и, db_path=q._enrich_db, email=em)
        card = q._card_for(и)
        full = build_panel(inn=и or None, email=em, letter_subject=тема, letter_body=тело,
                           company=ctx.get("company") or {}, emails=ctx.get("emails") or [],
                           signals=ctx.get("signals") or [], store=store, card=card, signature=подпись)
    except Exception as ex:  # noqa: BLE001
        сч["сбой сборки"] += 1; print("сбой #%s: %s" % (кид, str(ex)[:150]), flush=True); continue
    комп = full.get("company") or {}
    # данные ЦА там, где в обогащении пусто
    if not комп.get("activity"): комп["activity"] = (р.get("Продукция") or "")[:600]; комп["activity_source"] = "файл ЦА (CA-ENGER-ZALIVKA)"
    if not комп.get("site"): комп["site"] = р.get("Сайт") or с.get("Сайт") or ""
    if not комп.get("region"): комп["region"] = р.get("Регион") or ""
    if not комп.get("revenue") and (р.get("Выручка, млн ₽") or "").strip():
        комп["revenue_h"] = "%s млн ₽ (ЦА)" % р.get("Выручка, млн ₽")
    комп["why_basis"] = "Газ: %s. Отрасль: %s. Почему подходит: %s" % (з.get("gaz", ""), з.get("otr", "") or р.get("Отрасль основная", ""),
                                                                       (з.get("pochemu") or "")[:300])
    _обор = (с.get("Оборудование, линии") or "").strip()
    if not комп.get("why_equipment") or "не определено" in str(комп.get("why_equipment")):
        комп["why_equipment"] = ("Оборудование с сайта: %s" % _обор[:300]) if _обор else ("По ЦА: %s" % (р.get("Техпроцесс (где нужен газ)") or "")[:300])
    if not комп.get("name"): комп["name"] = (р.get("Компания") or "").replace("&quot;", '"')
    if not комп.get("division"): комп["division"] = "kc"; комп["division_badge"] = "КЦ (газ)"
    full["company"] = комп
    full["pochemu"] = (з.get("pochemu") or "")[:300]
    full["gaz"] = {"otrasl": з.get("otr", ""), "gaz": з.get("gaz", ""), "fraza": з.get("f", ""),
                   "priznaki_na_sayte": с.get("Признаки газа на сайте") or "", "gazy_pasport": с.get("Газы (паспорт)") or "",
                   "tehprocess": (р.get("Техпроцесс (где нужен газ)") or "")[:400]}
    for ключ in ("letter_division", "mailbox_id", "vruchnuyu", "adres_za_drugim_inn", "company_name_short"):
        if ключ in стар: full[ключ] = стар[ключ]
    # ПРАВИЛО ВЛАДЕЛЬЦА 11.11: мешает только письмо КЦ на ТОТ ЖЕ адрес < 15 дней (его ловит заслон confirm._guard).
    # «Контакт с компанией тем же направлением < 30 дней» (на другой адрес) — подсказка, а не удержание.
    _держат = [ф for ф in (full.get("stop_flags") or []) if str(ф.get("code") or "") != "recent_contact"]
    full.setdefault("actions", {})["confirm_hold"] = bool(_держат)
    for ф in full.get("stop_flags") or []:
        флаги[str(ф.get("code") or ф.get("kind") or ф.get("text") or ф)[:60]] += 1
    сч["стоп-флаг есть" if full.get("stop_flags") else "без стоп-флагов"] += 1
    сч["удержание (confirm_hold)" if full["actions"]["confirm_hold"] else "без удержания"] += 1
    сч["атрибуция ok" if (full.get("compliance") or {}).get("attribution_ok") else "атрибуции нет"] += 1
    if пример is None: пример = (кид, full)
    if ПРИМЕНИТЬ:
        for _п in range(12):
            try:
                with store._lock:
                    к.execute("UPDATE confirm_reviews SET panel_json=? WHERE id=? AND status='pending'", (json.dumps(full, ensure_ascii=False), кид))
                    к.commit()
                break
            except Exception as ex:  # noqa: BLE001
                if "locked" not in str(ex): raise
                time.sleep(10)
        сч["записано"] += 1
        if сч["записано"] % 100 == 0: print("записано %d" % сч["записано"], flush=True)
print("ИТОГ:", dict(сч), flush=True)
print("стоп-флаги:", dict(флаги.most_common(15)), flush=True)
if пример:
    print("пример #%s: company=%s\ncompliance=%s\nstop_flags=%s" % (пример[0], json.dumps(пример[1].get("company"), ensure_ascii=False)[:700],
          json.dumps(пример[1].get("compliance"), ensure_ascii=False)[:400], json.dumps(пример[1].get("stop_flags"), ensure_ascii=False)[:400]), flush=True)
