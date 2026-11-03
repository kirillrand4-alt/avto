# -*- coding: utf-8 -*-
"""Напоминания v2: чистка ошибок + деление на две версии (владелец 02.11: «давай
часть вернём, но запугивающую часть из шестого варианта перепишем»).

1) В pending-карточках v2 правим плеоназмы и канцелярит прямо в тексте
   («тестовое испытание» -> «тестирование», «на безвозмездной основе» ->
   «бесплатно»…); карточки с обратным порядком слов и непонятными словами
   («Благодарна будет», «Полезны можем», «пейнерли») снимаем.
2) Половину оставшихся компаний (по ИНН, детерминированно) снимаем с v2 и
   пишем список _ops/napominaniya-ab-zahody.json — им пойдут вопросы-заходы
   пилота (napominaniya_pilot.py spisok=…). Версия B остаётся шаблоном редактора.
    napominaniya_ab.py [--primenit]"""
import hashlib, io, json, re, sqlite3, sys
from datetime import datetime
ЗАМЕНЫ = [(r"тестов\w* испытани\w*", None), (r"на безвозмездной основе", "бесплатно"),
          (r"на бесплатной основе", "бесплатно"), (r"\bбез оплаты\b", "бесплатно"),
          (r"\s+с вашей стороны", "")]
ТЕСТ = {"тестовое испытание": "тестирование", "тестового испытания": "тестирования",
        "тестовому испытанию": "тестированию", "тестовым испытанием": "тестированием",
        "тестовом испытании": "тестировании", "тестовые испытания": "тестирование"}
СНЯТЬ = re.compile(r"благодарн\w* буд|признательн\w* буд|полезн\w* можем|пейнерли|удалось ли (?:передать|направить|донести)|"
                   r"обращение удалось ли|сортировки (?:молока|сливок|воды|сока|масла)", re.I)
ПРИМ = "--primenit" in sys.argv
з = [json.loads(s) for s in io.open(r"C:\sender\_ops\napominaniya-v2.jsonl", encoding="utf-8")]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
т = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
правлено = снято = 0
живые = []
for x in з:
    if not x.get("karta"):
        continue
    р = c.execute("SELECT status, body, inn, panel_json FROM confirm_reviews WHERE id=?", (x["karta"],)).fetchone()
    if not р or р[0] != "pending" or "заходы" in (р[3] or ""):   # карточка уже отдана заходам
        continue
    тело = р[1] or ""
    if СНЯТЬ.search(тело):
        снято += 1
        if ПРИМ:
            with c:
                c.execute("UPDATE confirm_reviews SET status='skipped', reason='напоминание v2: ошибка оборота', decided_at=?, updated_at=? WHERE id=? AND status='pending'", (т, т, x["karta"]))
        continue
    нов = тело
    for к, в in ТЕСТ.items():
        нов = re.sub(к, в, нов, flags=re.I)
    for рег, в in ЗАМЕНЫ:
        if в is not None:
            нов = re.sub(рег, в, нов, flags=re.I)
    if нов != тело:
        правлено += 1
        if ПРИМ:
            with c:
                c.execute("UPDATE confirm_reviews SET body=?, updated_at=? WHERE id=? AND status='pending'", (нов, т, x["karta"]))
    живые.append((x["karta"], str(р[2] or x["inn"])))
# деление пополам по ИНН
в_заходы = [(k, инн) for k, инн in живые if int(hashlib.md5(инн.encode()).hexdigest(), 16) % 2 == 0]
print("pending v2: %d после чистки | правлено текстов %d | снято с ошибкой %d | в заходы %d, остаётся шаблон %d"
      % (len(живые), правлено, снято, len(в_заходы), len(живые) - len(в_заходы)))
if ПРИМ:
    with c:
        for k, _ in в_заходы:
            c.execute("UPDATE confirm_reviews SET status='skipped', reason='напоминание v2: версия заходов (A/B 02.11)', decided_at=?, updated_at=? WHERE id=? AND status='pending'", (т, т, k))
    json.dump([инн for _, инн in в_заходы], io.open(r"C:\sender\_ops\napominaniya-ab-zahody.json", "w", encoding="utf-8"))
    print("список для заходов записан")
else:
    print("СУХОЙ ПРОГОН")
