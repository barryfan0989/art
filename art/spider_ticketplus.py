from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from lxml import etree
from urllib.parse import quote
from datetime import datetime
import time
import re
import requests
import pymysql


# =========================
# MySQL
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
# Chrome
# =========================
options = Options()
options.add_argument("--start-maximized")

driver = webdriver.Chrome(options=options)


# =========================
# artist clean
# =========================
def extract_artist(name):
    if not name:
        return ""

    name = re.sub(r"\s+", " ", name).strip()
    name = re.split(r"\s+in\s+", name, flags=re.IGNORECASE)[0].strip()
    name = re.sub(r"\b20\d{2}\b", "", name)
    name = re.sub(r"(TOUR|CONCERT|FANMEETING|LIVE|WORLD|ASIA|SHOW|FEST|SPECIAL|ANNIVERSARY)",
                  "", name, flags=re.IGNORECASE)
    name = re.sub(r"[《》【】()\[\]（）<>：:|·–—\-]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


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
# parse datetime
# =========================
def parse_datetime(date_str, time_str):
    date_str = re.sub(r"\(.*?\)", "", date_str).strip()
    date_str = date_str.replace(".", "-").replace("/", "-")

    start = time_str.split("~")[0].strip()
    dt = f"{date_str} {start}"

    try:
        return datetime.strptime(dt, "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M:%S")
    except:
        return None


# =========================
# price parse
# =========================
def parse_price(text):
    if not text:
        return []

    text = re.sub(r"\s+", " ", text)

    match = re.findall(r"(預售|現場)\s*(\d+)", text)
    return match


# =========================
# main
# =========================
driver.get("https://ticketplus.com.tw/")
time.sleep(5)


while True:

    old_count = len(driver.find_elements(By.XPATH, '//div[contains(@class,"text-title")]'))
    print("當前活動數:", old_count)

    try:
        btn = driver.find_element(By.XPATH, '//button[contains(.,"查看更多活動")]')
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(3)
    except:
        break


# scroll
last_h = 0
same = 0

while same < 3:
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(3)

    h = driver.execute_script("return document.body.scrollHeight")

    if h == last_h:
        same += 1
    else:
        same = 0

    last_h = h


# =========================
# parse list
# =========================
xml = etree.HTML(driver.page_source)
cards = xml.xpath('//*[@id="app"]//main//div[contains(@class,"col")]')

print("TOTAL:", len(cards))


for card in cards:

    try:
        name = ''.join(card.xpath('.//div[contains(@class,"text-title")]//text()')).strip()
        if not name:
            continue

        style = ''.join(card.xpath('.//*[contains(@style,"background-image")][1]/@style'))
        m = re.search(r'event/([^/]+)', style)

        if not m:
            continue

        eid = m.group(1)
        link = f"https://ticketplus.com.tw/activity/{eid}"

        driver.get(link)
        time.sleep(4)

        detail = etree.HTML(driver.page_source)

        # ======================
        # fields
        # ======================
        date_raw = ''.join(detail.xpath('//*[@id="buyTicket"]//div[2]//text()'))
        time_raw = ''.join(detail.xpath('//*[@id="buyTicket"]//div[3]//text()'))
        venue_raw = ''.join(detail.xpath('//*[@id="buyTicket"]//div[4]//text()'))

        activity_date = parse_datetime(date_raw, time_raw)
        venue = re.sub(r'\s+', ' ', venue_raw).strip()

        issuance_raw = ''.join(detail.xpath('//*[@id="activityInfo"]//p[5]//span[2]//text()'))
        issuance = None

        if issuance_raw:
            try:
                clean = re.sub(r"啟售｜", "", issuance_raw)
                m2 = re.search(r"(\d{4}[.\-/]\d{2}[.\-/]\d{2}).*?(\d{1,2}:\d{2})", clean)
                if m2:
                    d = m2.group(1).replace(".", "-").replace("/", "-")
                    t = m2.group(2)
                    issuance = datetime.strptime(f"{d} {t}", "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M:%S")
            except:
                issuance = None

        price_raw = ''.join(detail.xpath('//*[@id="activityInfo"]//p[5]//span[1]//text()'))

        price_list = parse_price(price_raw)

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
            "ticketplus",
            issuance,
            activity_date,
            link,
            now()
        ))

        conn.commit()
        event_id = cursor.lastrowid

        # ======================
        # ticket
        # ======================
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
