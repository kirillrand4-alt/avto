# -*- coding: utf-8 -*-
"""Показать кусок Confirm.tsx вокруг карточки «Кому пишем»."""
import io
import sys
т = io.open(r"C:\sender\sender\web\src\screens\Confirm.tsx",
            encoding="utf-8").read().splitlines()
якорь = sys.argv[1] if len(sys.argv) > 1 else 'title="Кому пишем"'
до = int(sys.argv[2]) if len(sys.argv) > 2 else 30
после = int(sys.argv[3]) if len(sys.argv) > 3 else 40
for i, с in enumerate(т):
    if якорь in с:
        for н in range(max(0, i - до), min(len(т), i + после)):
            print("%5d| %s" % (н + 1, т[н][:150]))
        print("-----")
print("=== КУСОК CONFIRM ===")
