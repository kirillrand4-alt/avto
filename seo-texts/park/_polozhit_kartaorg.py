# Кладёт задание на карточки организаций из хранилища дропа в C:\sender.
# Через base64-аргумент не проходит: 800 записей дают слишком длинную командную строку
# («Argument list too long»), тот же случай, что с заданием на съёмку.
import shutil, os, json
src = r'C:\seostat\drop\drop-storage\PARK-KARTAORG-ZADANIE-1S.json'
dst = r'C:\sender\_kartaorg.json'
shutil.copyfile(src, dst)
print('положено:', dst, os.path.getsize(dst), 'записей:', len(json.load(open(dst, encoding='utf-8'))))
