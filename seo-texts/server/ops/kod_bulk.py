# -*- coding: utf-8 -*-
import io
т = io.open(r"C:\sender\sender\api\app.py", encoding="utf-8", errors="replace").read()
i = т.find("def confirm_bulk_to_auto")
j = т.find("\n    @app.", i + 10)
print(т[т.find("rows.sort", i):j if j > 0 else i + 4000][:3200])
