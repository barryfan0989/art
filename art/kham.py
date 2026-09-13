import requests
import re
import pymysql
from lxml import etree
from urllib.parse import quote
from datetime import datetime

# =========================
# DB
# =========================
conn = pymysql.connect(
    host="ticketdb-ticket63.f.aivencloud.com",
    port=13599,
    user="avnadmin",
    password="AVNS_QqNVFqacdQinAgGmXY9",
    database="defaultdb",
    charset="utf8mb4"
)
cursor = conn.cursor()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe(v):
    return v if v else None


# =========================
# cookies / headers
# =========================
cookies = {
    # 原始 cookies（保留即可）
}

headers = {
    'user-agent': 'Mozilla/5.0',
    'accept-language': 'zh-TW,zh-Hant;q=0.9,zh;q=0.8'
}


# =========================
# artist clean
# =========================
def extract_artist(name):
    if not name:
        return ""

    name = re.sub(r"\s+", " ", name).strip()
    name = re.split(r"\s+in\s+", name, flags=re.IGNORECASE)[0].strip()
    name = re.sub(r"\b20\d{2}\b", "", name)

    name = re.sub(
        r"(TOUR|CONCERT|FANMEETING|LIVE|WORLD|ASIA|SHOW|FEST|SPECIAL|ANNIVERSARY)",
        "",
        name,
        flags=re.IGNORECASE
    )

    name = re.sub(r"[《》【】()\[\]（）<>：:|·–—\-]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


# =========================
# KHAM 時間解析
# =========================
def parse_ticket_time(html):
    activity_date = None
    issuance = None

    if not html:
        return activity_date, issuance

    tree = etree.HTML(html)
    text = tree.xpath("string(.)")

    m1 = re.search(
        r'釋票啟售.*?(\d{4})年(\d{1,2})月(\d{1,2})日.*?(\d{1,2})點',
        text
    )
    if m1:
        issuance = f"{m1.group(1)}-{m1.group(2).zfill(2)}-{m1.group(3).zfill(2)} {m1.group(4).zfill(2)}:00:00"

    m2 = re.search(
        r'(演出時間|活動時間).*?(\d{4})年(\d{1,2})月(\d{1,2})日.*?(\d{1,2})點',
        text
    )
    if m2:
        activity_date = f"{m2.group(2)}-{m2.group(3).zfill(2)}-{m2.group(4).zfill(2)} {m2.group(5).zfill(2)}:00:00"

    return activity_date, issuance


# =========================
# wiki
# =========================
def get_wiki_info(artist):
    language = ""
    classify = ""
    outline = ""

    if not artist:
        return language, classify, outline

    try:
        url = f"https://zh.wikipedia.org/zh-tw/{quote(artist)}"
        html = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "zh-TW,zh-Hant;q=0.9,zh;q=0.8"}, timeout=15).text
        xml = etree.HTML(html)

        country = ''.join(xml.xpath(
            '//*[@id="mw-content-text"]//table[1]//tr[4]/td//text()'
        )).strip()

        if any(k in country for k in ["日本"]):
            language = "日語"
        elif any(k in country for k in ["韓國"]):
            language = "韓語"
        elif any(k in country for k in ["美國", "英國"]):
            language = "英語"
        else:
            language = "華語"

        classify = "、".join(xml.xpath(
            '//*[@id="mw-content-text"]//table[1]//tr[5]/td//a/text()'
        ))

        ps = xml.xpath('//*[@id="mw-content-text"]//p')
        txt = []

        for p in ps:
            t = ''.join(p.xpath('.//text()'))
            t = re.sub(r'\[\d+\]', '', t).strip()
            if any(err in t for err in ["可能出現此提示", "維基百科目前還沒有名為", "本頁面目前沒有內容"]):
                continue
            if len(t) > 10:
                txt.append(t)
            if len(txt) >= 4:
                break

        outline = "\n".join(txt)

    except:
        pass

    return language, classify, outline


# =========================
# KHAM list
# =========================
def get_list():
    url = "https://kham.com.tw/application/utk01/UTK0101_03.aspx"
    r = requests.get(url, cookies=cookies, headers=headers, timeout=20)
    xml = etree.HTML(r.text)

    links = xml.xpath('//*[@id="show-area"]/div[2]/div/a/@href')
    titles = xml.xpath('//*[@id="show-area"]/div[2]/div/a/p//text()')

    for link, name in zip(links, titles):
        link = "https://kham.com.tw/application" + link
        link = link.replace("application..", "application/")
        yield name.strip(), link


# =========================
# MAIN
# =========================
for name, link in get_list():

    try:
        html = requests.get(link, headers=headers, cookies=cookies, timeout=20).text
        tree = etree.HTML(html)

        now_time = now()

        # =====================
        # KHAM fields
        # =====================
        activity_date, issuance = parse_ticket_time(html)

        venue = ''.join(tree.xpath('//*[contains(text(),"地點")]/following::*//text()'))[:200]
        venue = re.sub(r"\s+", " ", venue).strip() or None

        price_raw = ''.join(tree.xpath('//*[contains(text(),"票價")]/following::*//text()'))
        price_raw = re.sub(r"\s+", " ", price_raw)

        price_list = re.findall(r"(預售|現場)\s*(\d+)", price_raw)

        artist = extract_artist(name)

        language, classify, outline = get_wiki_info(artist)

        # =====================
        # venue
        # =====================
        cursor.execute("SELECT id FROM venues WHERE name=%s", (venue,))
        v = cursor.fetchone()

        if v:
            venue_id = v[0]
        else:
            cursor.execute(
                "INSERT INTO venues(name,address) VALUES(%s,%s)",
                (venue, venue)
            )
            conn.commit()
            venue_id = cursor.lastrowid

        # =====================
        # event
        # =====================
        cursor.execute("""
            INSERT INTO events(
                venue_id,name,source_site,
                ticket_sale_time,event_time,
                event_url,scraped_at
            )
            VALUES(%s,%s,%s,%s,%s,%s,%s)
        """, (
            venue_id,
            name,
            "kham",
            issuance,
            activity_date,
            link,
            now_time
        ))

        conn.commit()
        event_id = cursor.lastrowid

        # =====================
        # ticket
        # =====================
        if not price_list:
            cursor.execute("""
                INSERT INTO event_tickets(event_id,ticket_type,price)
                VALUES(%s,%s,%s)
            """, (event_id, "未解析", -1))
        else:
            for t, p in price_list:
                cursor.execute("""
                    INSERT INTO event_tickets(event_id,ticket_type,price)
                    VALUES(%s,%s,%s)
                """, (event_id, t, p))

        # =====================
        # artist
        # =====================
        cursor.execute("SELECT id FROM artists WHERE name=%s", (artist,))
        a = cursor.fetchone()

        if a:
            artist_id = a[0]
        else:
            cursor.execute("""
                INSERT INTO artists(name,wiki_intro,wiki_url)
                VALUES(%s,%s,%s)
            """, (artist, outline, ""))
            conn.commit()
            artist_id = cursor.lastrowid

        # =====================
        # bridge
        # =====================
        cursor.execute("""
            INSERT IGNORE INTO event_artists(event_id,artist_id)
            VALUES(%s,%s)
        """, (event_id, artist_id))

        conn.commit()

        print("OK:", name)

    except Exception as e:
        print("ERROR:", name, e)
        conn.rollback()
