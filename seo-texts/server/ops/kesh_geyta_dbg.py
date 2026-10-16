import sys
sys.path.insert(0, r"C:\sender")
import gen_provider
from sender import target_gate as tg
print("ГРАНИЦЫ:", gen_provider._ГРАНИЦЫ, "| длина ПРОДАВЕЦ+СХЕМА:", len(tg.ПРОДАВЕЦ + tg.СХЕМА), "| файл:", gen_provider.__file__)
