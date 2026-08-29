# -*- coding: utf-8 -*-
"""Стоп-лист спрашиваем ДО генерации, а не только на отправке."""
import io
import json
import os
import py_compile
import time

ПУТЬ = r"C:\sender\sender\ai_quota.py"
МЕТКА = '_v_stop_liste'
ЗАМЕНЫ = json.loads(r'''[["    def _dead_addresses(self, emails: list) -> set:", "    def _v_stop_liste(self, poluchateli: list) -> set:\n        \"\"\"id получателей, чей адрес, домен или ИНН уже в стоп-листе.\n\n        Одним запросом на все три разреза, а не по вызову на кандидата:\n        кандидатов сканируется вдесятеро больше лимита. Истёкшие записи не\n        считаем — стоп-лист умеет быть временным.\n        \"\"\"\n        if not poluchateli:\n            return set()\n        адреса, домены, инны = set(), set(), set()\n        карта = {}\n        for r in poluchateli:\n            почта = str(getattr(r, \"email\", \"\") or \"\").strip().lower()\n            инн = \"\".join(c for c in str(getattr(r, \"inn\", \"\") or \"\")\n                          if c.isdigit())\n            домен = почта.split(\"@\")[-1] if \"@\" in почта else \"\"\n            if почта:\n                адреса.add(почта)\n            if домен:\n                домены.add(домен)\n            if инн:\n                инны.add(инн)\n            карта[r.id] = (почта, домен, инн)\n        значения = list(адреса | домены | инны)\n        найдено = set()\n        try:\n            con = sqlite3.connect(self._db_path, timeout=10)\n            try:\n                теперь = datetime.now(timezone.utc).strftime(\"%Y-%m-%dT%H:%M:%S\")\n                for i in range(0, len(значения), 400):\n                    часть = значения[i:i + 400]\n                    q = \",\".join(\"?\" * len(часть))\n                    найдено |= {str(x[0]).strip().lower() for x in con.execute(\n                        \"SELECT value FROM suppression \"\n                        \" WHERE LOWER(value) IN (%s) \"\n                        \"   AND (expires_at IS NULL OR expires_at > ?)\" % q,\n                        часть + [теперь])}\n            finally:\n                con.close()\n        except Exception:  # noqa: BLE001 - нет таблицы/сбой → никого не режем\n            logger.exception(\"стоп-лист при отборе не прочитан\")\n            return set()\n        if not найдено:\n            return set()\n        return {rid for rid, (почта, домен, инн) in карта.items()\n                if почта in найдено or домен in найдено or инн in найдено}\n\n    def _dead_addresses(self, emails: list) -> set:"], ["            out = [r for r in out\n                   if (r.email or \"\").strip().lower() not in мёртвые]", "            out = [r for r in out\n                   if (r.email or \"\").strip().lower() not in мёртвые]\n        # СТОП-ЛИСТ ЖИВЬЁМ, А НЕ ПО ФЛАГУ В КАРТОЧКЕ. Отбор выше просит\n        # query_recipients({'suppressed': False}), но это ФЛАГ получателя, и он\n        # отстаёт: адрес попадает в таблицу suppression по отбивке, а флаг в\n        # карточке остаётся прежним. Замер 28.08: 277 писем сгенерировано на\n        # адреса из стоп-листа, у 256 запись там появилась РАНЬШЕ письма — мы\n        # платили за генерацию, уже зная, что ящика нет. Ловил их только заслон\n        # отправки (259 черновиков сняты, 61 отказ за один день) — то есть\n        # деньги и место в партии уходили впустую.\n        в_стопе = self._v_stop_liste(out)\n        if в_стопе:\n            logger.info(\"стоп-лист: пропущено %s получателей\", len(в_стопе))\n            out = [r for r in out if r.id not in в_стопе]"]]''')

т = io.open(ПУТЬ, encoding="utf-8").read()
if МЕТКА in т:
    print("правка уже стоит")
    raise SystemExit(0)
for стар, нов in ЗАМЕНЫ:
    if т.count(стар) != 1:
        print("ЯКОРЬ НЕ ОДИН (%d): %r" % (т.count(стар), стар[:70]))
        raise SystemExit(1)
было = т
for стар, нов in ЗАМЕНЫ:
    т = т.replace(стар, нов)
бэк = ПУТЬ + ".bak-%d" % int(time.time())
with io.open(бэк, "w", encoding="utf-8", newline="") as f:
    f.write(было); f.flush(); os.fsync(f.fileno())
with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
    f.write(т); f.flush(); os.fsync(f.fileno())
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as ex:
    with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
        f.write(было); f.flush(); os.fsync(f.fileno())
    print("НЕ КОМПИЛИРУЕТСЯ, откатил: %s" % ex)
    raise SystemExit(1)
print("готово: %d -> %d знаков, бэкап %s" % (len(было), len(т), os.path.basename(бэк)))
