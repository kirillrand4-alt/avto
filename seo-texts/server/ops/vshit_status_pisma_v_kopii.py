# -*- coding: utf-8 -*-
"""Хирургическая правка kopii_avtootveta: статус брать и у ПИСЬМА.

Метод соседней сессии читает статус КАРТОЧКИ. Пока копии отправляли
руками, этого хватало: живая отправка ставит карточке 'sent'. Но
автоотправка помечает ПИСЬМО, а карточка остаётся 'approved' - и лента
про семь доставленных писем говорит «одобрена, уходит», а про одно
недоставленное (550 invalid mailbox) - то же самое.

Правим по месту, файл целиком не переписываем: store.py общий, и там
живёт чужая работа.
"""
import hashlib
import io
import shutil
import time

ФАЙЛ = r"C:\sender\sender\store.py"
ЯКОРЬ = '''            из.setdefault(исходный, []).append({
                "email": r["email"], "status": r["status"],
                "ts": r["ts"],
                "chelovecheski": _KOPIYA_PO_RUSSKI.get(
                    str(r["status"]), str(r["status"])),
            })
'''
НОВОЕ = '''            # СТАТУС ПИСЬМА СИЛЬНЕЕ СТАТУСА КАРТОЧКИ. Пока копии слали
            # руками, хватало карточки: живая отправка ставит ей 'sent'.
            # Автоотправка помечает ПИСЬМО, а карточка остаётся 'approved' -
            # и лента про доставленную копию говорила «одобрена, уходит», а
            # про отбитую (550 invalid mailbox) - ровно то же самое.
            слово = _KOPIYA_PO_RUSSKI.get(str(r["status"]), str(r["status"]))
            состояние = str(r["status"])
            пм = self._conn.execute(
                "SELECT m.status s, COALESCE(m.last_error,'') e "
                "  FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id "
                " WHERE cr.dedup_key=?", (str(r["dedup_key"]),)).fetchone()
            if пм is not None:
                if str(пм["s"]) == "sent":
                    слово, состояние = "отправлена", "sent"
                elif str(пм["s"]) == "failed":
                    почему = str(пм["e"] or "")[:70]
                    слово = "не доставлена" + (f": {почему}" if почему else "")
                    состояние = "failed"
                elif str(пм["s"]) == "skipped" and состояние != "skipped":
                    слово = "снята перед отправкой"
                    состояние = "skipped"
            из.setdefault(исходный, []).append({
                "email": r["email"], "status": состояние,
                "ts": r["ts"],
                "chelovecheski": слово,
            })
'''
s = io.open(ФАЙЛ, encoding="utf-8").read()
if "СТАТУС ПИСЬМА СИЛЬНЕЕ СТАТУСА КАРТОЧКИ" in s:
    print("уже вшито")
    raise SystemExit(0)
if s.count(ЯКОРЬ) != 1:
    print(f"якорь найден {s.count(ЯКОРЬ)} раз - не трогаю")
    raise SystemExit(2)
рез = ФАЙЛ + ".bak-" + time.strftime("%m%d-%H%M")
shutil.copy2(ФАЙЛ, рез)
io.open(ФАЙЛ, "w", encoding="utf-8").write(s.replace(ЯКОРЬ, НОВОЕ))
print("бэкап:", рез)
print("sha после:", hashlib.sha256(io.open(ФАЙЛ, "rb").read()).hexdigest()[:16])
import py_compile                                                # noqa: E402
py_compile.compile(ФАЙЛ, doraise=True)
print("компилируется")
