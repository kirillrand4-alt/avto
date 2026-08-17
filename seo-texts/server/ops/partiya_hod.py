# -*- coding: utf-8 -*-
"""Последние письма: вызовов, срывов, цена — чтобы понять, письмо это или срыв."""
import io, json, os, time
Ж = r"C:\sender\_ops\gen-partiya-935.jsonl"
z = [json.loads(s) for s in io.open(Ж, encoding="utf-8") if s.strip()]
print(f"записей {len(z)} | ок {sum(1 for x in z if x.get('ок'))} | "
      f"${sum(float(x.get('цена_$') or 0) for x in z):.2f}")
print("последняя запись:", time.strftime(
    '%H:%M:%S', time.localtime(os.path.getmtime(Ж))),
    "| сейчас:", time.strftime('%H:%M:%S'))
print("\nпоследние 12 записей:")
print(f"{'имя':<30}{'ок':<5}{'сек':<6}{'выз':<5}{'срыв':<6}{'$':<8}")
for x in z[-12:]:
    print(f"{str(x.get('имя'))[:28]:<30}"
          f"{'да' if x.get('ок') else 'нет':<5}"
          f"{x.get('сек', '?'):<6}{x.get('вызовов', '?'):<5}"
          f"{x.get('срывов', 0):<6}{float(x.get('цена_$') or 0):<8.3f}")
свежие = [x for x in z if x.get("вызовов")]
if свежие:
    сс = sum(x.get("срывов", 0) for x in свежие)
    сv = sum(x.get("вызовов", 0) for x in свежие)
    print(f"\nпо записям с учётом: вызовов {сv}, срывов {сс} "
          f"({100 * сс // max(1, сv)}%)")
    цена_ок = [float(x.get('цена_$') or 0) for x in свежие if x.get("ок")]
    if цена_ок:
        цена_ок.sort()
        print(f"цена вышедшего письма: медиана ${цена_ок[len(цена_ок)//2]:.3f}, "
              f"мин ${цена_ок[0]:.3f}, макс ${цена_ок[-1]:.3f}")
