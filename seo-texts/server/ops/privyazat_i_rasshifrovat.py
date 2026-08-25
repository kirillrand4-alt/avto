# -*- coding: utf-8 -*-
"""Привязать «Шато де Талю» и расшифровать кракозябры в карточке «Техно-ГМ».

КРАКОЗЯБРЫ. Письмо пришло в UTF-8, а разобрано как cp1251 — «Мы рады
приветствовать» превратилось в «РњС‹ СЂР°РґС‹», а панель показала ещё один
слой перекодировки. Лечится обратной дорогой: текст кодируем cp1251 и
читаем как utf-8. Делаем до двух проходов и НИ РАЗУ не наугад: результат
принимаем, только если кириллицы в нём стало больше.
"""
import re
import sqlite3
import sys

ДЕЛАТЬ = "primenit" in sys.argv[1:]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
# СТРОЧНЫЕ русские буквы, без re.I: в кракозябрах «РњС‹ СЂР°РґС‹» полно
# ЗАГЛАВНЫХ Р и С — они тоже кириллица, и счёт без учёта регистра давал
# мусору такую же оценку, как живому тексту. Живая русская фраза почти вся
# строчная, вот на это и смотрим.
_КИР = re.compile(r"[а-яё]")


def доля_кириллицы(т):
    т = str(т or "")
    return (sum(1 for с in т if _КИР.match(с)) / len(т)) if т else 0.0


def расшифровать(т):
    """Снять слои неверной перекодировки, пока текст становится русским."""
    лучший = str(т or "")
    for _ in range(2):
        try:
            # errors="ignore": в хвосте письма сидит ВТОРОЙ слой перекодировки
            # («НЏвЂЊ»), он в cp1251 не лезет и строгим кодированием ронял
            # всю расшифровку. Выбрасываем нечитаемое — это уже мусор, а
            # русский текст письма восстанавливается целиком. Порчу
            # страхует проверка ниже: принимаем, только если строчной
            # кириллицы стало больше.
            попытка = лучший.encode("cp1251", errors="ignore").decode(
                "utf-8", errors="ignore")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if доля_кириллицы(попытка) <= доля_кириллицы(лучший):
            break
        лучший = попытка
    return лучший


# ---- 1. Шато де Талю: живой вопрос про стоимость и КП ---------------------
карточка = c.execute("SELECT id, email, company_name FROM leads "
                     " WHERE LOWER(email)='andryushchenko@chateaudetalu.ru'"
                     ).fetchone()
цель = c.execute("SELECT id, company_name, inn FROM recipients "
                 " WHERE LOWER(email)='sale@chateaudetalu.ru'").fetchone()
print("карточка %s -> компания %s (ИНН %s, получатель #%s)"
      % (карточка["id"] if карточка else "нет",
         цель["company_name"] if цель else "нет",
         цель["inn"] if цель else "-", цель["id"] if цель else "-"))

# ---- 2. Техно-ГМ: расшифровка ---------------------------------------------
крако = c.execute("SELECT id, email, need FROM leads "
                  " WHERE LOWER(email)='kulikov@texno-gm.com'").fetchone()
if крако:
    было = крако["need"] or ""
    стало = расшифровать(было)
    print("\nбыло  (%.0f%% кириллицы): %s" % (100 * доля_кириллицы(было), было[:90]))
    print("стало (%.0f%% кириллицы): %s" % (100 * доля_кириллицы(стало), стало[:200]))

if not ДЕЛАТЬ:
    print("\nвхолостую. Применить — primenit")
    raise SystemExit(0)

if карточка and цель:
    c.execute("UPDATE leads SET recipient_id=?, company_name=?, inn=?, "
              "       version=version+1, updated_at=datetime('now') WHERE id=?",
              (цель["id"], цель["company_name"], цель["inn"], карточка["id"]))
    print("привязано: карточка %s -> %s" % (карточка["id"], цель["company_name"]))
if крако and расшифровать(крако["need"] or "") != (крако["need"] or ""):
    c.execute("UPDATE leads SET need=?, version=version+1, "
              "       updated_at=datetime('now') WHERE id=?",
              (расшифровать(крако["need"]), крако["id"]))
    print("расшифровано: карточка %s" % крако["id"])
c.commit()
for р in c.execute("SELECT id, email, company_name, inn, substr(need,1,90) need "
                   "  FROM leads WHERE id IN (?,?)",
                   (карточка["id"] if карточка else 0, крако["id"] if крако else 0)):
    print("   %s" % dict(р))
