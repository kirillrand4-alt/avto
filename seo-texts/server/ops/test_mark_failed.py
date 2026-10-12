# -*- coding: utf-8 -*-
"""Проверка mark_failed на временной базе: ящик не закрепляется при повторе."""
import importlib.util as _iu
import os
import sys
import tempfile
sys.path.insert(0, r"C:\sender")
сп = _iu.spec_from_file_location("store_t", r"C:\sender\sender\store.py")
м = _iu.module_from_spec(сп)
sys.modules["store_t"] = м
сп.loader.exec_module(м)
путь = os.path.join(tempfile.mkdtemp(), "t.db")
s = м.Store(путь)
s.init_schema()
c = s._conn
now = "2026-10-12T00:00:00"
c.execute("INSERT INTO campaigns (id,name,status,legal_entity,legal_inn,created_at,"
          "updated_at) VALUES (1,'t','draft','x','1',?,?)", (now, now))
c.execute("INSERT INTO recipients (id,email,domain,created_at,updated_at) "
          "VALUES (1,'a@b.ru','b.ru',?,?)", (now, now))
c.execute("INSERT INTO sequence_steps (id,campaign_id,step_index,delay_hours,"
          "subject_tmpl,body_tmpl,created_at) VALUES (1,1,0,0,'s','b',?)", (now,))
for i in (1, 2):
    c.execute("INSERT INTO messages (id,idempotency_key,campaign_id,recipient_id,"
              "sequence_step_id,status,created_at,updated_at) VALUES "
              "(?,?,1,1,1,'sending',?,?)", (i, "k%d" % i, now, now))
c.commit()
s.mark_failed(1, "connect failed", retryable=True, mailbox_id="v.kuzmin@x.ru")
s.mark_failed(2, "550 no such user", retryable=False, mailbox_id="v.kuzmin@x.ru")
for р in c.execute("SELECT id,status,mailbox_id,last_error FROM messages"):
    print("   письмо %s: статус %-9s ящик %-14s ошибка %s" % tuple(р))
r1 = c.execute("SELECT mailbox_id,last_error FROM messages WHERE id=1").fetchone()
r2 = c.execute("SELECT mailbox_id FROM messages WHERE id=2").fetchone()
ок = (r1[0] is None and r1[1].startswith("[v.kuzmin") and r2[0] == "v.kuzmin@x.ru")
print("=== ТЕСТ MARK_FAILED: %s ===" % ("ОК" if ок else "ПРОВАЛ"))
