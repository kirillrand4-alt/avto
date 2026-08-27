import hashlib, io, os
for f in ("confirm.py", "store.py"):
    п = os.path.join(r"C:\sender\sender", f)
    д = io.open(п, "rb").read()
    print("%-12s %6d байт  %s" % (f, len(д), hashlib.sha256(д).hexdigest()[:16]))
