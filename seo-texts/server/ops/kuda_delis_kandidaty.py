# -*- coding: utf-8 -*-
"""Куда делись кандидаты генерации: по журналу и логу — отсев по причинам, пачки без фраз;
для 51 «общей фразы» — что было в последнем прогоне по их ИНН."""
import collections, io, json, re, sqlite3
for имя in ("zakupshchiki-kc", "imennye-kc"):
    з = [json.loads(s) for s in io.open(r"C:\sender\_ops\%s.jsonl" % имя, encoding="utf-8")]
    от = collections.Counter(re.sub(r"\d{6,}|'.*|%r.*", "", x["otsev"])[:45] for x in з if x.get("otsev"))
    лог = io.open(r"C:\sender\_ops\%s.log" % имя, encoding="utf-8", errors="replace").read()
    print("==", имя, "| заведено:", sum(1 for x in з if not x.get("otsev")), "| отсев:", dict(от))
    print("   пачек без фраз:", len(re.findall("модель не дала фраз", лог)), "|", re.findall(r"пачка \d+: модель не дала фраз: [^\n]{0,90}", лог)[-2:])
s = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
инн = {str(r[0]) for r in s.execute("SELECT cr.inn FROM confirm_reviews cr JOIN campaigns c ON c.id=cr.campaign_id WHERE c.name='КЦ по имени 06.11' AND cr.status='skipped' AND cr.reason LIKE 'общая фраза%'")}
посл = {}
for s_ in io.open(r"C:\sender\_ops\imennye-kc.jsonl", encoding="utf-8"):
    x = json.loads(s_)
    if x["inn"] in инн: посл[x["inn"]] = x
print("51 общая фраза: в журнале после снятия:", collections.Counter((x.get("otsev") or "заведено")[:60] for x in посл.values()).most_common(5))
