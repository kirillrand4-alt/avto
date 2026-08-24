import hashlib, io
b = io.open(r"C:\sender\sender\probe_sync.py", "rb").read()
print("probe_sync.py md5=%s  %d байт" % (hashlib.md5(b).hexdigest()[:12], len(b)))
print("есть ли уже правка:", "approved" in b.decode("utf-8", "replace")
      and "_очередь" in b.decode("utf-8", "replace"))
