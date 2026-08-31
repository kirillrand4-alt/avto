# -*- coding: utf-8 -*-
"""Забрать с дропа ТОЛЬКО те вердикты, которых ещё нет в addr_probe.

Штатный ProbeSync.забрать() перечитывает весь probe-rezultat.jsonl (22 097
строк) и по каждой строке лезет в базу — на боевом объёме это не укладывается
в потолок задания. Скачивание при этом мгновенное (4,6 МБ), то есть узкое
место не сеть, а 22 тысячи обращений к базе.

Здесь делаем то же самое, но только для новых строк. Побочные действия
сохраняем один в один: всеядный домен превращает «есть» в «принимает всё»,
мёртвый адрес снимает письмо с очереди и уходит в стоп-лист, вердикт едет
в обогащение.
"""
import json
import sys
import time
import urllib.request
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.addr_probe import (build_addr_probe, ЕСТЬ, НЕТ_MX,   # noqa: E402
                               НЕТ_ЯЩИКА, НЕЯСНО, ПРИНИМАЕТ_ВСЁ)
from sender.config import Config                              # noqa: E402
from sender.dtos import SuppressionIn                         # noqa: E402
from sender.probe_sync import build_probe_sync, РЕЗУЛЬТАТ     # noqa: E402
from sender.store import Store                                # noqa: E402

СУХО = "--suho" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
проба = getattr(build_addr_probe(store, cfg), "probe_", None)
цикл = build_probe_sync(store, проба, cfg)

база, токен = цикл._ключи()
з = urllib.request.Request("%s/%s" % (база, РЕЗУЛЬТАТ))
з.add_header("X-Drop-Token", токен)
т0 = time.time()
with urllib.request.urlopen(з, timeout=300) as о:
    строки = о.read().decode("utf-8", "replace").splitlines()
print("скачано строк: %d за %.1f с" % (len(строки), time.time() - т0))

всеядные = цикл._domeny_prinimayut_vsyo()
новые = []
уже = 0
for с in строки:
    с = с.strip()
    if not с:
        continue
    try:
        z = json.loads(с)
    except Exception:                                         # noqa: BLE001
        continue
    адрес = str(z.get("email") or "").strip().lower()
    вердикт = str(z.get("verdict") or "")
    if not адрес or not вердикт:
        continue
    if вердикт == ЕСТЬ and адрес.rsplit("@", 1)[-1] in всеядные:
        вердикт = ПРИНИМАЕТ_ВСЁ
        z["answer"] = "домен принимает любой адрес — подтверждения нет"
    стоял = проба.cached(адрес)
    if стоял and str(стоял.get("verdict") or "") == вердикт:
        уже += 1
        continue
    z["verdict"] = вердикт
    новые.append(z)

print("уже в базе: %d; к импорту: %d" % (уже, len(новые)))
if СУХО or not новые:
    print("\n[сухой прогон или импортировать нечего]")
    raise SystemExit(0)

# карточки очереди только по нужным адресам — дешевле, чем читать 100k строк
адреса = {str(z["email"]).strip().lower() for z in новые}
по_почте = {}
with store._lock:
    for ряд in store._conn.execute(
            "SELECT id, message_id, lower(trim(email)) e FROM confirm_reviews"
            " WHERE status IN ('pending','approved','edited')"
            "   AND lower(trim(email)) IN (%s)"
            % ",".join("?" * len(адреса)), sorted(адреса)).fetchall():
    	по_почте.setdefault(ряд["e"], []).append(dict(ряд))
print("карточек очереди по этим адресам: %d"
      % sum(len(v) for v in по_почте.values()))

свод, снято, в_стоп = Counter(), 0, 0
для_обогащения = []
т1 = time.time()
for z in новые:
    адрес, вердикт = str(z["email"]).strip().lower(), z["verdict"]
    проба._save(адрес, вердикт, z.get("code"), str(z.get("answer") or ""),
                str(z.get("mx") or ""))
    свод[вердикт] += 1
    для_обогащения.append({"email": адрес, "verdict": вердикт,
                           "answer": z.get("answer")})
    if вердикт not in (НЕТ_ЯЩИКА, НЕТ_MX, НЕЯСНО):
        continue
    причина = ("у домена нет почтового сервера: %s" % str(z.get("answer") or "")[:60]
               if вердикт == НЕТ_MX else
               "проба не добилась ответа: %s" % str(z.get("answer") or "")[:60]
               if вердикт == НЕЯСНО else
               "адрес не существует: %s %s" % (z.get("code"),
                                               str(z.get("answer") or "")[:60]))
    for r in по_почте.get(адрес, []):
        ок = False
        try:
            ок = bool(store.confirm_decide(int(r["id"]), status="skipped",
                                           decided_by="проба адресов (внешний сервер)",
                                           reason=причина))
        except Exception:                                     # noqa: BLE001
            pass
        if not ок and r.get("message_id"):
            try:
                ок = bool(store.mark_skipped_if_not_terminal(
                    int(r["message_id"]),
                    "проба адресов (внешний сервер): %s" % причина))
            except Exception:                                 # noqa: BLE001
                pass
        if ок:
            снято += 1
    if вердикт == НЕЯСНО:
        continue
    try:
        store.suppression_add(SuppressionIn(scope="email", value=адрес,
                                            reason="bounce_hard",
                                            source="probe-worker"))
        в_стоп += 1
    except Exception:                                         # noqa: BLE001
        pass

в_обогащении = {}
try:
    from sender.probe_enrich import записать as _в_обогащение
    в_обогащении = _в_обогащение(цикл.enrich_db, для_обогащения)
except Exception as e:                                        # noqa: BLE001
    print("в обогащение не доехало: %s" % str(e)[:100])

print("\n=== ИТОГ ИМПОРТА (%.1f с) ===" % (time.time() - т1))
for в, n in свод.most_common():
    print("   %-16s %5d" % (в, n))
print("снято писем с очереди: %d; адресов в стоп-лист: %d" % (снято, в_стоп))
print("в обогащение: %s" % str(в_обогащении)[:160])
