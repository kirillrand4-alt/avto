# -*- coding: utf-8 -*-
"""Дописать в тип Lead поля, которые лента теперь получает от API."""
import io
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
п = r'C:\sender\sender\web\src\api\types.ts'
t = io.open(п, encoding='utf-8', errors='replace').read()
якорь = """  // open-tracking: сколько раз «открыл» (справочно, в РФ приблизительно)
  opens?: number;
}"""
новое = """  // open-tracking: сколько раз «открыл» (справочно, в РФ приблизительно)
  opens?: number;
  // «Отправляли» — батч-флаг из send_log (Фича 2)
  sent?: { ever: boolean; last_ts: string | null; replied: boolean;
           within_90d: boolean } | null;
  // НАШ последний ответ этой компании: лента показывает «↩ время», чтобы было
  // видно, что разговор уже начат (владелец 19.08: «где вот он?»)
  otvet?: { ts: string | null; subject: string | null;
            review_id: number; status: string } | null;
}"""
if 'otvet?' in t:
    print(json.dumps({'уже_есть': True}, ensure_ascii=False))
else:
    assert якорь in t, 'якорь не найден'
    io.open(п, 'w', encoding='utf-8').write(t.replace(якорь, новое))
    print(json.dumps({'дописано': ['sent', 'otvet']}, ensure_ascii=False))
