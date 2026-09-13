from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from lxml import etree
import time
import re
from datetime import datetime
from urllib.parse import quote
import pymysql
import requests


# ======================
# MySQL
# ======================
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


# ======================
# Chrome
# ======================
options = Options()
options.add_argument("--start-maximized")

driver = webdriver.Chrome(options=options)


# ======================
# list
# ======================
def get_list():
    driver.get("https://tixcraft.com/")
    time.sleep(6)

    xml = etree.HTML(driver.page_source)

    links = xml.xpath('//*[@id="upcoming-activity"]/div/div//a/@href')
    names = xml.xpath('//*[@id="upcoming-activity"]/div/div//img/@title')

    data = []

    for n, l in zip(names, links):
        if not l.startswith("http"):
            l = "https://tixcraft.com" + l
        data.append((n, l))

    return data


# ======================
# artist
# ======================
def extract_artist(name):
    if not name:
        return ""

    name = re.sub(r"\s+", " ", name).strip()
    name = re.split(r"\s+in\s+", name, flags=re.I)[0].strip()
    name = re.sub(r"\b20\d{2}\b", "", name)
    name = re.sub(r"(TOUR|CONCERT|LIVE|SHOW|FEST|SPECIAL)", "", name, flags=re.I)
    name = re.sub(r"[《》【】()（）<>：:|·–—\-]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


# ======================
# wiki
# ======================
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

        if "日本" in country:
            language = "日語"
        elif "韓國" in country:
            language = "韓語"
        elif "美國" in country or "英國" in country:
            language = "英語"
        else:
            language = "華語"

        classify = "、".join(xml.xpath(
            '//*[@id="mw-content-text"]//table[1]//tr[5]/td//a/text()'
        ))

        ps = xml.xpath('//*[@id="mw-content-text"]//p')

        txt = []
        for p in ps:
            t = ''.join(p.xpath('.//text()')).strip()
            t = re.sub(r'\[\d+\]', '', t)
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


# ======================
# parse detail
# ======================
def parse_detail(url):
    driver.get(url)
    time.sleep(4)

    xml = etree.HTML(driver.page_source)

    now_time = now()

    # 售票時間
    issuance = ""
    p = xml.xpath('//*[@id="intro"]/p[18]')

    if p:
        text = ''.join(p[0].xpath('.//text()'))
        m = re.search(r"(\d{4}/\d{1,2}/\d{1,2}).*?(\d{1,2}:\d{2})", text)
        if m:
            y, mo, d = m.group(1).split("/")
            h, mi = m.group(2).split(":")
            issuance = f"{y}-{mo.zfill(2)}-{d.zfill(2)} {h.zfill(2)}:{mi}:00"

    # 活動時間
    activity_dates = []
    for p in xml.xpath('//*[@id="intro"]/p'):
        t = ''.join(p.xpath('.//text()')).strip()
        m = re.search(r"(\d{4}/\d{1,2}/\d{1,2}).*?(\d{1,2}:\d{2})", t)
        if m:
            y, mo, d = m.group(1).split("/")
            h, mi = m.group(2).split(":")
            activity_dates.append(f"{y}-{mo.zfill(2)}-{d.zfill(2)} {h.zfill(2)}:{mi}:00")

    activity_date = activity_dates[0] if activity_dates else None

    # venue
    v = ''.join(xml.xpath('//*[@id="intro"]/p[16]//text()')).strip()
    venue = re.sub(r"：", "", v).strip()

    # tickets
    tickets = []
    for p in xml.xpath('//*[@id="intro"]/p[position()>39]'):
        text = ''.join(p.xpath('.//text()')).strip()

        if not text:
            continue

        m = re.match(r"(.+?)\s*(\d{3,5})$", text)
        if m:
            tickets.append((m.group(1).strip(), int(m.group(2))))

    return issuance, activity_date, venue, tickets, now_time


# ======================
# main
# ======================
for name, link in get_list():

    try:
        issuance, activity_date, venue, tickets, now_time = parse_detail(link)

        artist = extract_artist(name)
        language, classify, outline = get_wiki_info(artist)

        # ======================
        # venue
        # ======================
        cursor.execute("SELECT id FROM venues WHERE name=%s", (venue,))
        v = cursor.fetchone()

        if v:
            venue_id = v[0]
        else:
            cursor.execute("INSERT INTO venues(name,address) VALUES(%s,%s)", (venue, venue))
            conn.commit()
            venue_id = cursor.lastrowid

        # ======================
        # event
        # ======================
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
            "tixcraft",
            safe(issuance),
            safe(activity_date),
            link,
            now_time
        ))

        conn.commit()
        event_id = cursor.lastrowid

        # ======================
        # tickets
        # ======================
        if not tickets:
            cursor.execute("""
                INSERT INTO event_tickets(event_id,ticket_type,price)
                VALUES(%s,%s,%s)
            """, (event_id, "未解析", -1))
        else:
            for t, p in tickets:
                cursor.execute("""
                    INSERT INTO event_tickets(event_id,ticket_type,price)
                    VALUES(%s,%s,%s)
                """, (event_id, t, p))

        # ======================
        # artist
        # ======================
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

        # ======================
        # bridge
        # ======================
        cursor.execute("""
            INSERT IGNORE INTO event_artists(event_id,artist_id)
            VALUES(%s,%s)
        """, (event_id, artist_id))

        conn.commit()

        print("OK:", name)

    except Exception as e:
        print("ERROR:", name, e)
        conn.rollback()


driver.quit()
