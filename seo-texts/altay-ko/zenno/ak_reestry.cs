// ak_reestry.cs - кубик ZennoPoster: открыть закрытый реестр/площадку и сохранить HTML.
// Вставляется ОДНИМ блоком "Свой код" (Own code, C#). Ничего не возвращает (блок void), поэтому
// компилируется в любом проекте. Капчу решает штатный кубик ZennoPoster ПОСЛЕ этого блока:
// если капча найдена, код пишет "1" в переменную kapcha_est и выходит - дальше по ветке ставьте
// свой кубик распознавания и снова этот же блок с переменной prodolzhit=1.
//
// Папка обмена (переменная проекта obmen; по умолчанию C:\seostat\drop\zenno):
//   ak_zadaniya.txt   вход:  <id>;<источник>;<url>;<текст_которого_ждать>
//   ak_otdano.txt     кто уже взят в работу
//   ak_gotovo\        выход: <id>.html, <id>_p2.html ...
//   ak_vypolneno.txt  <id> \t <источник> \t <страниц> \t ok
//   ak_otkazy.txt     <id> \t <источник> \t причина
//   proxy.txt         прокси, по строке
//
// Переменные проекта, все необязательные: obmen, stranic (по умолч. 40), zhdat_sek (60).
// Кубик выставляет переменные: zadanie_id, zadanie_istochnik, zadanie_url, stranic_sohraneno, kapcha_est.

string obmen = project.Variables["obmen"].Value;
if (string.IsNullOrEmpty(obmen)) obmen = @"C:\seostat\drop\zenno";

int maxStranic = 40;
int.TryParse(project.Variables["stranic"].Value, out maxStranic);
if (maxStranic <= 0) maxStranic = 40;

int zhdatSek = 60;
int.TryParse(project.Variables["zhdat_sek"].Value, out zhdatSek);
if (zhdatSek <= 0) zhdatSek = 60;

string fZad = System.IO.Path.Combine(obmen, "ak_zadaniya.txt");
string fOtdano = System.IO.Path.Combine(obmen, "ak_otdano.txt");
string dGotovo = System.IO.Path.Combine(obmen, "ak_gotovo");
string fVyp = System.IO.Path.Combine(obmen, "ak_vypolneno.txt");
string fOtk = System.IO.Path.Combine(obmen, "ak_otkazy.txt");
System.IO.Directory.CreateDirectory(dGotovo);

// ---------- 1. взять задание. Mutex вместо SyncObjects: работает между потоками и процессами
string zadanie = "";
System.Threading.Mutex zamok = new System.Threading.Mutex(false, "ak_reestry_ochered");
try
{
    zamok.WaitOne(30000);
    System.Collections.Generic.List<string> vzyaty = new System.Collections.Generic.List<string>();
    if (System.IO.File.Exists(fOtdano))
    {
        string[] ot = System.IO.File.ReadAllLines(fOtdano);
        for (int i = 0; i < ot.Length; i++) vzyaty.Add(ot[i].Trim());
    }
    if (System.IO.File.Exists(fZad))
    {
        string[] vse = System.IO.File.ReadAllLines(fZad, System.Text.Encoding.UTF8);
        for (int i = 0; i < vse.Length; i++)
        {
            string s = vse[i].Trim();
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
    project.Variables["zadanie_id"].Value = "";
    return;
}

string[] chasti = zadanie.Split(';');
string id = chasti[0].Trim();
string istochnik = chasti.Length > 1 ? chasti[1].Trim() : "";
string url = chasti.Length > 2 ? chasti[2].Trim() : "";
string zhdatTekst = chasti.Length > 3 ? chasti[3].Trim() : "";
project.Variables["zadanie_id"].Value = id;
project.Variables["zadanie_istochnik"].Value = istochnik;
project.Variables["zadanie_url"].Value = url;
project.SendInfoToLog("задание " + id + " (" + istochnik + ") " + url, true);

// ---------- 2. прокси
try
{
    string fProxy = System.IO.Path.Combine(obmen, "proxy.txt");
    if (System.IO.File.Exists(fProxy))
    {
        string[] pr = System.IO.File.ReadAllLines(fProxy);
        System.Collections.Generic.List<string> zhivye = new System.Collections.Generic.List<string>();
        for (int i = 0; i < pr.Length; i++) if (pr[i].Trim().Length > 5) zhivye.Add(pr[i].Trim());
        if (zhivye.Count > 0)
        {
            Random rnd = new Random(Guid.NewGuid().GetHashCode());
            instance.SetProxy(zhivye[rnd.Next(zhivye.Count)]);
        }
    }
}
catch (Exception e) { project.SendWarningToLog("прокси не поставился: " + e.Message, true); }

// ---------- 3. открыть, дождаться текста, сохранить, пройти пагинацию
int stranicSohraneno = 0;
string prichina = "";
bool kapchaEst = false;
try
{
    instance.ActiveTab.Navigate(url, "");
    instance.ActiveTab.WaitDownloading();

    DateTime kray = DateTime.Now.AddSeconds(zhdatSek);
    bool dozhdalis = false;
    while (DateTime.Now < kray)
    {
        instance.ActiveTab.WaitDownloading();
        string h = instance.ActiveTab.DocumentText;
        if (h == null) h = "";
        if (h.IndexOf("captcha", StringComparison.OrdinalIgnoreCase) >= 0 ||
            h.IndexOf("recaptcha", StringComparison.OrdinalIgnoreCase) >= 0 ||
            h.IndexOf("подтвердите, что вы не робот", StringComparison.OrdinalIgnoreCase) >= 0)
        {
            kapchaEst = true;
        }
        if (zhdatTekst.Length == 0)
        {
            if (h.Length > 5000) { dozhdalis = true; break; }
        }
        else if (h.IndexOf(zhdatTekst, StringComparison.OrdinalIgnoreCase) >= 0)
        {
            dozhdalis = true; break;
        }
        System.Threading.Thread.Sleep(2000);
    }

    if (!dozhdalis)
    {
        prichina = kapchaEst ? "капча" : ("не дождались текста: " + zhdatTekst);
    }
    else
    {
        for (int p = 1; p <= maxStranic; p++)
        {
            string html = instance.ActiveTab.DocumentText;
            if (html == null) html = "";
            if (html.Length < 500) { prichina = "пустая страница на " + p.ToString(); break; }
            string imya = (p == 1) ? (id + ".html") : (id + "_p" + p.ToString() + ".html");
            System.IO.File.WriteAllText(System.IO.Path.Combine(dGotovo, imya), html, System.Text.Encoding.UTF8);
            stranicSohraneno = p;

            HtmlElement dalee = instance.ActiveTab.FindElementByAttribute("a", "class", "pagination__next", "text", 0);
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
}
catch (Exception e) { prichina = e.Message; }

// ---------- 4. отчёт
System.Threading.Mutex zamok2 = new System.Threading.Mutex(false, "ak_reestry_otchet");
try
{
    zamok2.WaitOne(30000);
    if (stranicSohraneno > 0)
        System.IO.File.AppendAllText(fVyp, id + "\t" + istochnik + "\t" + stranicSohraneno.ToString() + "\tok\r\n", System.Text.Encoding.UTF8);
    else
        System.IO.File.AppendAllText(fOtk, id + "\t" + istochnik + "\t" + (prichina.Length > 0 ? prichina : "без страниц") + "\r\n", System.Text.Encoding.UTF8);
}
finally { zamok2.ReleaseMutex(); }

project.Variables["stranic_sohraneno"].Value = stranicSohraneno.ToString();
project.Variables["kapcha_est"].Value = kapchaEst ? "1" : "0";
project.SendInfoToLog("готово " + id + ": страниц " + stranicSohraneno.ToString() + (prichina.Length > 0 ? (" | " + prichina) : ""), true);
