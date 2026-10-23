# -*- coding: utf-8 -*-
"""Корректор починенных писем КЦ-1 (владелец 23.10: «давай» на «прогнать 747
починенных писем через дешёвую модель как корректора: только грамматика и
согласование»). Поймано 23.10: «мощности уже не хватают».

Берёт карточки из _ops/dopisannye-kc1.jsonl (review_id), только ещё НЕ
отправленные (карточка pending, либо approved с письмом scheduled). Модель
правит ТОЛЬКО грамматику/согласование/опечатки и отдаёт текст между метками.
Правку принимаем, если она маленькая: похожесть >= 0.97, слов ±3, абзацев
столько же, концовка «С уважением,» на месте, длинного тире нет. Иначе — тело
не трогаем. Новое тело — в confirm_reviews.body (прежнее — в журнал
_ops/korrektor-kc1.jsonl, резюм по нему). Отсоединённый процесс.
    korrektor_dopisannyh.py --zapusk | (без ключа — ход)"""
import difflib
import io
import json
import os
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ЖУР = r"C:\sender\_ops\korrektor-kc1.jsonl"
МОДЕЛЬ = os.environ.get("KORREKTOR_MODEL", "claude-haiku-4-5")
if "--zapusk" in sys.argv:
    л = io.open(r"C:\sender\_ops\korrektor-kc1.log", "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--rabota"], cwd=r"C:\sender",
                         stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    time.sleep(20)
    print("корректор запущен, pid %d, жив %s" % (п.pid, п.poll() is None))
    sys.exit(0)
if "--rabota" not in sys.argv:
    from collections import Counter
    try:
        з = [json.loads(s) for s in io.open(ЖУР, encoding="utf-8")]
    except OSError:
        з = []
    print("обработано:", len(з), Counter(x.get("итог") for x in з).most_common())
    for x in [x for x in з if x.get("итог") == "исправлено"][-5:]:
        print("  #%s: %s" % (x["review_id"], x.get("правки")))
    sys.exit(0)

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
import gen_provider as GP  # noqa: E402

c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
сделано = set()
if os.path.exists(ЖУР):
    сделано = {json.loads(s)["review_id"] for s in io.open(ЖУР, encoding="utf-8")}
ids = [json.loads(s).get("review_id") for s in io.open(r"C:\sender\_ops\dopisannye-kc1.jsonl", encoding="utf-8")]
ids = [i for i in dict.fromkeys(ids) if i and i not in сделано]
карточки = []
for i in ids:
    r = c.execute("SELECT c.id, c.status, c.body, m.status FROM confirm_reviews c LEFT JOIN messages m ON m.id=c.message_id "
                  "WHERE c.id=?", (i,)).fetchone()
    if r and r[2] and (r[1] == "pending" or (r[1] in ("approved", "edited") and r[3] == "scheduled")):
        карточки.append((r[0], r[2]))
c.close()
print(time.strftime("%H:%M:%S"), "к проверке:", len(карточки), flush=True)
ЗАДАНИЕ = """Ты корректор русского текста. Исправь в письме ТОЛЬКО грамматические
ошибки, согласование слов (род, число, падеж), опечатки и пунктуацию. НЕ меняй
смысл, порядок, стиль, слова, абзацы и длину. Не добавляй и не убирай фразы.
Не ставь длинное тире. Если ошибок нет — верни текст без изменений.

Ответ: только исправленный текст между строками <<<ТЕКСТ и ТЕКСТ>>>.

<<<ТЕКСТ
{тело}
ТЕКСТ>>>"""


def одна(карточка):
    rid, тело = карточка
    try:
        m = GP._raw_stream([{"role": "user", "content": ЗАДАНИЕ.format(тело=тело)}], МОДЕЛЬ, 2500,
                           thinking=False, effort="low")
        т = m if isinstance(m, str) else "".join(getattr(b, "text", "") for b in getattr(m, "content", []) or [])
        н, к = т.rfind("<<<ТЕКСТ"), т.rfind("ТЕКСТ>>>")
        if н < 0 or к < 0 or к < н:
            return rid, тело, None, "нет меток в ответе"
        нов = т[н + len("<<<ТЕКСТ"):к].strip("\n").rstrip()
        return rid, тело, нов, None
    except Exception as ex:  # noqa: BLE001
        return rid, тело, None, "сбой: " + str(ex)[:120]


def правки(а, б):
    сл_а, сл_б = а.split(), б.split()
    out = []
    for оп, i1, i2, j1, j2 in difflib.SequenceMatcher(None, сл_а, сл_б).get_opcodes():
        if оп != "equal":
            out.append("%s → %s" % (" ".join(сл_а[i1:i2]), " ".join(сл_б[j1:j2])))
    return out


ж = io.open(ЖУР, "a", encoding="utf-8")
with ThreadPoolExecutor(max_workers=6) as пул:
    for rid, тело, нов, ош in пул.map(одна, карточки):
        запись = {"review_id": rid}
        if ош or not нов:
            запись["итог"] = ош or "пусто"
        elif нов.strip() == тело.strip():
            запись["итог"] = "без ошибок"
        else:
            пр = правки(тело, нов)
            похож = difflib.SequenceMatcher(None, тело, нов).ratio()
            if (похож < 0.97 or abs(len(тело.split()) - len(нов.split())) > 3
                    or тело.count("\n\n") != нов.count("\n\n") or "—" in нов
                    or ("С уважением," in тело) != ("С уважением," in нов)):
                запись.update(итог="правка слишком большая — не взята", правки=пр[:6], похожесть=round(похож, 3))
            else:
                cx = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
                with cx:
                    cx.execute("UPDATE confirm_reviews SET body=?, updated_at=? WHERE id=? AND status IN "
                               "('pending','approved','edited')", (нов, time.strftime("%Y-%m-%dT%H:%M:%S"), rid))
                cx.close()
                запись.update(итог="исправлено", правки=пр[:6], было=тело)
        ж.write(json.dumps(запись, ensure_ascii=False) + "\n")
        ж.flush()
        os.fsync(ж.fileno())
print(time.strftime("%H:%M:%S"), "готово", flush=True)
