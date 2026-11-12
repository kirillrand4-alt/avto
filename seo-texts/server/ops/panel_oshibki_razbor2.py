# -*- coding: utf-8 -*-
"""Контекст TimeoutError и 500 почты в логах панели + адрес письма 21116 (только чтение)."""
import io, os, re, sqlite3
def хвост(путь, n=3000000):
    р = os.path.getsize(путь)
    with io.open(путь, "rb") as f: f.seek(max(0, р - n)); return f.read().decode("utf-8", "replace").splitlines()
е = хвост(r"C:\sender\_ops\panel_err.log")
for k, x in enumerate(е):
    if x.startswith("TimeoutError") or "imap" in x.lower() and "Error" in x:
        print("---- стек перед строкой %d:" % k); print("\n".join(y[:180] for y in е[max(0, k - 14):k + 1]))
о = хвост(r"C:\sender\_ops\panel_out.log", 3000000)
print("404:", sorted(set(re.sub(r"\?.*", "", x.split('"')[1])[:80] for x in о if '" 404' in x))[:12])
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
р = c.execute("SELECT m.campaign_id, m.status, m.attempt_count, r.email FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.id=21116").fetchone()
print("письмо 21116:", р[:3], "адрес не-ASCII:", bool(р and re.search(r"[^\x00-\x7f]", р[3] or "")), "домен:", (р[3] or "").split("@")[-1] if р else "")
