# -*- coding: utf-8 -*-
import hashlib, io
d = io.open(r"C:\sender\sender\imap_watcher.py", "rb").read()
print("сервер: %d байт  %s" % (len(d), hashlib.sha256(d).hexdigest()[:12]))
