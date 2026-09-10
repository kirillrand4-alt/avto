// ak_reestry.cs - кубик ZennoPoster: открыть закрытый реестр/площадку через прокси и сохранить HTML.
// Один блок "Свой код" (Own code, C#), возвращает null. Версия 4: НИ ОДНОЙ обязательной переменной проекта -
// если переменной нет, берётся значение по умолчанию (в v3 отсутствие obmen роняло кубик: "No such variable").
// Также: перебор прокси при 403, прогрев на главной домена, снятие BOM, возврат задания в очередь при отказе.
//
// Папка обмена (по умолчанию C:\seostat\drop\zenno):
//   ak_zadaniya.txt   вход:  <id>;<источник>;<url>;<текст_которого_ждать>
//   proxy.txt         прокси, по строке, вид socks5://логин:пароль@ip:порт
//   ak_otdano.txt     кто уже взят в работу
//   ak_gotovo\        выход: <id>.html, <id>_p2.html ...
//   ak_vypolneno.txt  <id> \t <источник> \t <страниц> \t ok
//   ak_otkazy.txt     <id> \t <источник> \t причина
//
// Необязательные переменные проекта: obmen, stranic (40), zhdat_sek (60), popytok_proxy (4).
// Если в проекте заведены zadanie_id, zadanie_istochnik, zadanie_url, stranic_sohraneno, kapcha_est -
// кубик их заполнит; если нет - молча пропустит.

// ---------- 0. безопасное чтение переменных проекта: отсутствие переменной не должно ронять кубик
string obmen = @"C:\seostat\drop\zenno";
try { string v = project.Variables["obmen"].Value; if (!string.IsNullOrEmpty(v)) obmen = v; } catch (Exception) { }

int maxStranic = 40;
try { string v = project.Variables["stranic"].Value; int n; if (int.TryParse(v, out n) && n > 0) maxStranic = n; } catch (Exception) { }

int zhdatSek = 60;
try { string v = project.Variables["zhdat_sek"].Value; int n; if (int.TryParse(v, out n) && n > 0) zhdatSek = n; } catch (Exception) { }

int popytokProxy = 4;
try { string v = project.Variables["popytok_proxy"].Value; int n; if (int.TryParse(v, out n) && n > 0) popytokProxy = n; } catch (Exception) { }

string fZad = System.IO.Path.Combine(obmen, "ak_zadaniya.txt");
string fOtdano = System.IO.Path.Combine(obmen, "ak_otdano.txt");
string dGotovo = System.IO.Path.Combine(obmen, "ak_gotovo");
string fVyp = System.IO.Path.Combine(obmen, "ak_vypolneno.txt");
string fOtk = System.IO.Path.Combine(obmen, "ak_otkazy.txt");
System.IO.Directory.CreateDirectory(dGotovo);

// ---------- 1. взять задание. Mutex работает и между потоками, и между процессами
string zadanie = "";
System.Threading.Mutex zamok = new System.Threading.Mutex(false, "ak_reestry_ochered");
try
{
    zamok.WaitOne(30000);
    System.Collections.Generic.List<string> vzyaty = new System.Collections.Generic.List<string>();
    if (System.IO.File.Exists(fOtdano))
    {
        string[] ot = System.IO.File.ReadAllLines(fOtdano, System.Text.Encoding.UTF8);
        for (int i = 0; i < ot.Length; i++) vzyaty.Add(ot[i].Replace("\uFEFF", "").Trim());
    }
    if (System.IO.File.Exists(fZad))
    {
        string[] vse = System.IO.File.ReadAllLines(fZad, System.Text.Encoding.UTF8);
        for (int i = 0; i < vse.Length; i++)
        {
            string s = vse[i].Replace("\uFEFF", "").Trim();
            if (s.Length == 0) continue;
            string idt = s.Split(';')[0].Trim();
            if (vzyaty.Contains(idt)) continue;
            zadanie = s;
            System.IO.File.AppendAllText(fOtdano, idt + "\r\n", System.Text.Encoding.UTF8);
            break;
        }
    }
}
finally { zamok.ReleaseMutex(); }

if (zadanie.Length == 0)
{
    project.SendInfoToLog("задания кончились или нет файла " + fZad, true);
    try { project.Variables["zadanie_id"].Value = ""; } catch (Exception) { }
    return null;
}

string[] chasti = zadanie.Split(';');
string id = chasti[0].Trim();
string istochnik = chasti.Length > 1 ? chasti[1].Trim() : "";
string url = chasti.Length > 2 ? chasti[2].Trim() : "";
string zhdatTekst = chasti.Length > 3 ? chasti[3].Trim() : "";
try { project.Variables["zadanie_id"].Value = id; } catch (Exception) { }
try { project.Variables["zadanie_istochnik"].Value = istochnik; } catch (Exception) { }
try { project.Variables["zadanie_url"].Value = url; } catch (Exception) { }
project.SendInfoToLog("задание " + id + " (" + istochnik + ") " + url, true);

// корень домена для прогрева: у гос-порталов первый заход сразу в поиск часто ловит 403
string koren = url;
try
{
    Uri uu = new Uri(url);
    koren = uu.Scheme + "://" + uu.Host + "/";
}
catch (Exception) { koren = ""; }

// ---------- 2. список прокси, перемешанный
System.Collections.Generic.List<string> proxi = new System.Collections.Generic.List<string>();
try
{
    string fProxy = System.IO.Path.Combine(obmen, "proxy.txt");
    if (System.IO.File.Exists(fProxy))
    {
        string[] pr = System.IO.File.ReadAllLines(fProxy);
        for (int i = 0; i < pr.Length; i++) if (pr[i].Trim().Length > 5) proxi.Add(pr[i].Trim());
        Random rnd = new Random(Guid.NewGuid().GetHashCode());
        for (int i = proxi.Count - 1; i > 0; i--)
        {
            int j = rnd.Next(i + 1);
            string t = proxi[i]; proxi[i] = proxi[j]; proxi[j] = t;
        }
    }
}
catch (Exception e) { project.SendWarningToLog("прокси не прочитались: " + e.Message, true); }
if (proxi.Count == 0) project.SendWarningToLog("proxy.txt пуст - иду с голого адреса, гос-порталы его блокируют", true);

// ---------- 3. заходы: прокси за прокси, пока не откроется
int stranicSohraneno = 0;
string prichina = "";
bool kapchaEst = false;
bool otkrylos = false;
int zahodov = proxi.Count > 0 ? Math.Min(popytokProxy, proxi.Count) : 1;

for (int z = 0; z < zahodov && !otkrylos; z++)
{
    string tekushiyProxy = proxi.Count > 0 ? proxi[z] : "";
    try
    {
        if (tekushiyProxy.Length > 0) instance.SetProxy(tekushiyProxy);
        instance.ClearCookie();

        if (koren.Length > 0)
        {
            instance.ActiveTab.Navigate(koren, "");
            instance.ActiveTab.WaitDownloading();
            System.Threading.Thread.Sleep(2500);
        }

        instance.ActiveTab.Navigate(url, koren);
        instance.ActiveTab.WaitDownloading();

        DateTime kray = DateTime.Now.AddSeconds(zhdatSek);
        while (DateTime.Now < kray)
        {
            instance.ActiveTab.WaitDownloading();
            string h = instance.ActiveTab.FindElementByTag("html", 0).InnerHtml;
            if (h == null) h = "";

            if (h.IndexOf("403 Forbidden", StringComparison.OrdinalIgnoreCase) >= 0 ||
                h.IndexOf("Access to this resource is denied", StringComparison.OrdinalIgnoreCase) >= 0 ||
                h.IndexOf("429 Too Many Requests", StringComparison.OrdinalIgnoreCase) >= 0 ||
                h.IndexOf("Bad Request", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                prichina = "отказ адресу (403/429), меняю прокси";
                break;
            }
            if (h.IndexOf("captcha", StringComparison.OrdinalIgnoreCase) >= 0 ||
                h.IndexOf("recaptcha", StringComparison.OrdinalIgnoreCase) >= 0 ||
                h.IndexOf("подтвердите, что вы не робот", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                kapchaEst = true;
            }
            if (zhdatTekst.Length == 0)
            {
                if (h.Length > 5000) { otkrylos = true; break; }
            }
            else if (h.IndexOf(zhdatTekst, StringComparison.OrdinalIgnoreCase) >= 0)
            {
                otkrylos = true; break;
            }
            System.Threading.Thread.Sleep(2000);
        }

        if (!otkrylos && prichina.Length == 0)
            prichina = kapchaEst ? "капча" : ("не дождались текста: " + zhdatTekst);
    }
    catch (Exception e) { prichina = e.Message; }

    if (!otkrylos) project.SendWarningToLog("заход " + (z + 1).ToString() + " из " + zahodov.ToString() + " не удался: " + prichina, false);
}

// ---------- 4. сохранение страниц и пагинация
if (otkrylos)
{
    prichina = "";
    try
    {
        for (int p = 1; p <= maxStranic; p++)
        {
            string html = instance.ActiveTab.FindElementByTag("html", 0).InnerHtml;
            if (html == null) html = "";
            if (html.Length < 500) { prichina = "пустая страница на " + p.ToString(); break; }
            string imya = (p == 1) ? (id + ".html") : (id + "_p" + p.ToString() + ".html");
            System.IO.File.WriteAllText(System.IO.Path.Combine(dGotovo, imya), html, System.Text.Encoding.UTF8);
            stranicSohraneno = p;

            var dalee = instance.ActiveTab.FindElementByAttribute("a", "class", "pagination__next", "text", 0);
            if (dalee.IsVoid) dalee = instance.ActiveTab.FindElementByAttribute("a", "rel", "next", "text", 0);
            if (dalee.IsVoid) dalee = instance.ActiveTab.FindElementByAttribute("a", "innertext", "Следующая", "text", 0);
            if (dalee.IsVoid) dalee = instance.ActiveTab.FindElementByAttribute("a", "innertext", "Далее", "text", 0);
            if (dalee.IsVoid) dalee = instance.ActiveTab.FindElementByAttribute("a", "innertext", (p + 1).ToString(), "text", 0);
            if (dalee.IsVoid) break;

            dalee.Click();
            instance.ActiveTab.WaitDownloading();
            System.Threading.Thread.Sleep(2000);
        }
    }
    catch (Exception e) { prichina = e.Message; }
}

// ---------- 5. отчёт. Если ни один прокси не пустил - вернуть задание в очередь
System.Threading.Mutex zamok2 = new System.Threading.Mutex(false, "ak_reestry_otchet");
try
{
    zamok2.WaitOne(30000);
    if (stranicSohraneno > 0)
    {
        System.IO.File.AppendAllText(fVyp, id + "\t" + istochnik + "\t" + stranicSohraneno.ToString() + "\tok\r\n", System.Text.Encoding.UTF8);
    }
    else
    {
        System.IO.File.AppendAllText(fOtk, id + "\t" + istochnik + "\t" + (prichina.Length > 0 ? prichina : "без страниц") + "\r\n", System.Text.Encoding.UTF8);
        try
        {
            if (System.IO.File.Exists(fOtdano))
            {
                string[] ot = System.IO.File.ReadAllLines(fOtdano, System.Text.Encoding.UTF8);
                System.Text.StringBuilder sb = new System.Text.StringBuilder();
                for (int i = 0; i < ot.Length; i++)
                {
                    string s = ot[i].Replace("\uFEFF", "").Trim();
                    if (s.Length > 0 && s != id) sb.Append(s + "\r\n");
                }
                System.IO.File.WriteAllText(fOtdano, sb.ToString(), System.Text.Encoding.UTF8);
            }
        }
        catch (Exception) { }
    }
}
finally { zamok2.ReleaseMutex(); }

try { project.Variables["stranic_sohraneno"].Value = stranicSohraneno.ToString(); } catch (Exception) { }
try { project.Variables["kapcha_est"].Value = kapchaEst ? "1" : "0"; } catch (Exception) { }
project.SendInfoToLog("готово " + id + ": страниц " + stranicSohraneno.ToString() + (prichina.Length > 0 ? (" | " + prichina) : ""), true);

return null;
