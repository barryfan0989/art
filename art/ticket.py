from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from lxml import etree
import time
import re
from datetime import datetime
import pymysql
from urllib.parse import quote


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
# artist clean
# ======================
def extract_artist(name):
    if not name:
        return ""

    name = re.sub(r"\s+", " ", name).strip()
    name = re.split(r"\s+in\s+", name, flags=re.I)[0].strip()
    name = re.sub(r"\b20\d{2}\b", "", name)
    name = re.sub(r"(TOUR|CONCERT|FANMEETING|LIVE|WORLD|ASIA|SHOW|FEST|SPECIAL|ANNIVERSARY)",
                  "", name, flags=re.I)
    name = re.sub(r"[《》【】()\[\]（）<>：:|·–—\-]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


# ======================
# wiki（requests OK）
# ======================
def get_wiki_info(artist):
    language = ""
    classify = ""
    outline = ""

    if not artist:
        return language, classify, outline

    try:
        url = f"https://zh.wikipedia.org/zh-tw/{quote(artist)}"

        import requests
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
# Selenium 配置
# ======================
options = Options()
options.add_argument("--start-maximized")

driver = webdriver.Chrome(options=options)


# ======================
# list request（Selenium）
# ======================
def get_list():
    url = "https://ticket.com.tw/application/UTK01/UTK0101_06.aspx?TYPE=1&CATEGORY=205"

    driver.get(url)
    time.sleep(6)

    xml = etree.HTML(driver.page_source)

    links = xml.xpath('//*[@id="shows"]/div/a/@href')
    names = xml.xpath('//*[@id="shows"]//h4/text()')

    data = []

    for name, link in zip(names, links):
        link = "https://ticket.com.tw/application" + link
        link = link.replace("application..", "application")
        data.append((name, link))

    print("列表數量:", len(data))
    return data


# ======================
# detail（Selenium 替代 requests）
# ======================
def get_detail(link):
    driver.get(link)
    time.sleep(5)

    xml = etree.HTML(driver.page_source)

    date_text = ''.join(xml.xpath(
        '//*[@id="ctl00_ContentPlaceHolder1_lbProgramInfo_Content"]/p[35]//text()'
    )).strip()

    time_text = ''.join(xml.xpath(
        '//*[@id="ctl00_ContentPlaceHolder1_lbProgramInfo_Content"]/p[37]//text()'
    )).strip()

    venue_text = ''.join(xml.xpath(
        '//*[@id="ctl00_ContentPlaceHolder1_lbProgramInfo_Content"]/p[38]//text()'
    )).strip()

    # ======================
    # date parse
    # ======================
    activity_date = ""

    try:
        date_text = date_text.replace("演出日期：", "").strip()

        m_date = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', date_text)
        m_time = re.search(r'(\d{1,2}:\d{2})', time_text)

        if m_date and m_time:
            y, m, d = m_date.groups()
            activity_date = datetime.strptime(
                f"{y}-{m}-{d} {m_time.group(1)}",
                "%Y-%m-%d %H:%M"
            ).strftime("%Y-%m-%d %H:%M:%S")

    except:
        activity_date = ""

    # venue
    venue = re.sub(r'^演出地點：', '', venue_text).strip()

    return activity_date, venue


# ======================
# main
# ======================
for name, link in get_list():

    try:
        activity_date, venue = get_detail(link)

        artist = extract_artist(name)
        language, classify, outline = get_wiki_info(artist)

        now_time = now()

        # ======================
        # venue
        # ======================
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
            "ticket.com.tw",
            None,
            safe(activity_date),
            link,
            now_time
        ))

        conn.commit()
        event_id = cursor.lastrowid

        # ======================
        # ticket（無結構兜底）
        # ======================
        cursor.execute("""
            INSERT INTO event_tickets(event_id,ticket_type,price)
            VALUES(%s,%s,%s)
        """, (event_id, "未解析", -1))

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

        print("=" * 60)
        print("活動:", name)
        print("藝人:", artist)
        print("時間:", activity_date)
        print("場館:", venue)
        print("來源:", "ticket.com.tw")
        print("狀態: OK")

    except Exception as e:
        print("ERROR:", name, e)
        conn.rollback()


driver.quit()