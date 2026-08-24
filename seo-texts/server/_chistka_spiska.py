# -*- coding: utf-8 -*-
r"""Убрать заглушку из списка очередей — список должен читаться как список."""
import json

ф = r'C:\sender\_tmp\web-pravki\screens\Leads.tsx'
т = open(ф, encoding='utf-8').read()
старое = """  const СВОИ_ОЧЕРЕДИ = ["in_bitrix", "qualified_hidden_placeholder",
                        "unqualified", "v_otpuske", "avtootvet",
                        "not_interested", "closed"]
    .filter((k) => k !== "qualified_hidden_placeholder");"""
новое = """  const СВОИ_ОЧЕРЕДИ = ["in_bitrix", "unqualified", "v_otpuske", "avtootvet",
                        "not_interested", "closed"];"""
d = {}
if новое in т:
    d['итог'] = 'уже чисто'
elif старое in т:
    open(ф, 'w', encoding='utf-8', newline='').write(т.replace(старое, новое, 1))
    d['итог'] = 'почищено'
else:
    d['итог'] = 'НЕ НАШЁЛ'
print(json.dumps(d, ensure_ascii=False))
