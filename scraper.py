import asyncio
import json
from datetime import datetime
import zoneinfo
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# ★ 検索対象サイトの設定リスト
TARGET_SITES = [
    # 1. atwiki
    {
        "site_name": "七浜国wiki",
        "type": "atwiki",
        "wiki_id": "nanahamakoku"
    },
    # 2. Google Sites群
    {
        "site_name": "Kirippe (Google Site)",
        "type": "google_sites",
        "base_url": "https://sites.google.com/view/kirippe/"
    },
    {
        "site_name": "Kiripe (Google Site)",
        "type": "google_sites",
        "base_url": "https://sites.google.com/view/kiripe/"
    },
    {
        "site_name": "霞野町 (Google Site)",
        "type": "google_sites",
        "base_url": "https://sites.google.com/view/kasumino-town/"
    },
    # 3. 一般Webサイト群
    {
        "site_name": "kiripe.tomidare.tokyo",
        "type": "generic",
        "start_url": "https://kiripe.tomidare.tokyo/"
    },
    {
        "site_name": "town.tomidare.tokyo",
        "type": "generic",
        "start_url": "https://town.tomidare.tokyo/"
    },
    {
        "site_name": "kirippe.tomidare.tokyo",
        "type": "generic",
        "start_url": "https://kirippe.tomidare.tokyo/"
    },
    # ★ 今回追加されたサイト群
    {
        "site_name": "日原ニュース",
        "type": "generic",
        "start_url": "https://awafgs.github.io/hihara_news/"
    },
    {
        "site_name": "七浜航空情報",
        "type": "generic",
        "start_url": "https://awafgs.github.io/NanahamaAirplaneInfo/"
    },
    {
        "site_name": "フロンティアビル案内",
        "type": "generic",
        "start_url": "https://awafgs.github.io/Frontier_Building/"
    },
    # 4. 単一ツール・単一ページ
    {
        "site_name": "ぬるぽ乗換案内",
        "type": "single_page",
        "url": "https://tomidare1234.github.io/nullpo_norikaeannai/"
    }
]

# --- atwiki 用スクレイパー ---
async def scrape_atwiki(page, site):
    wiki_id = site["wiki_id"]
    base_url = f"https://w.atwiki.jp/{wiki_id}/"
    list_url = f"{base_url}list"

    print(f"\n--- [atwiki: {site['site_name']}] 取得開始 ---")
    try:
        await page.goto(list_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
    except Exception as e:
        print(f"  └ 一覧取得失敗: {e}")
        return []

    soup = BeautifulSoup(await page.content(), "html.parser")
    page_urls = []
    for a_tag in soup.find_all("a", href=True):
        full_url = urljoin(base_url, a_tag["href"])
        if f"/{wiki_id}/pages/" in full_url and full_url.endswith(".html") and "login.atwiki.jp" not in full_url:
            if full_url not in page_urls:
                page_urls.append(full_url)

    data_list = []
    for index, url in enumerate(page_urls, 1):
        print(f"  [{index}/{len(page_urls)}] 取得中: {url}")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            page_soup = BeautifulSoup(await page.content(), "html.parser")
            title_elem = page_soup.find("h2", id="page_title")
            title = title_elem.text.strip() if title_elem else (page_soup.find("title").text.split("-")[0].strip() if page_soup.find("title") else "無題")

            body_elem = page_soup.find("div", id="wikibody") or page_soup.find("div", id="atwiki-body")
            body_text = " ".join(body_elem.text.split()) if body_elem else ""

            data_list.append({"site_name": site["site_name"], "title": title, "url": url, "content": body_text})
        except Exception as e:
            print(f"    └ スキップ: {e}")
    return data_list

# --- Google Sites 用スクレイパー ---
async def scrape_google_sites(page, site):
    base_url = site["base_url"]
    print(f"\n--- [Google Sites: {site['site_name']}] 取得開始 ---")

    try:
        await page.goto(base_url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)
    except Exception as e:
        print(f"  └ アクセス失敗: {e}")
        return []

    soup = BeautifulSoup(await page.content(), "html.parser")
    page_urls = [base_url]

    for a_tag in soup.find_all("a", href=True):
        full_url = urljoin(base_url, a_tag["href"])
        if full_url.startswith(base_url) and full_url not in page_urls:
            page_urls.append(full_url)

    data_list = []
    for index, url in enumerate(page_urls, 1):
        print(f"  [{index}/{len(page_urls)}] 取得中: {url}")
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)

            page_soup = BeautifulSoup(await page.content(), "html.parser")
            title = page_soup.find("title").text.strip() if page_soup.find("title") else "無題"
            body_text = " ".join(page_soup.body.text.split()) if page_soup.body else ""

            data_list.append({"site_name": site["site_name"], "title": title, "url": url, "content": body_text})
        except Exception as e:
            print(f"    └ スキップ: {e}")
    return data_list

# --- 一般Webサイト (自動巡回) 用スクレイパー ---
async def scrape_generic(page, site):
    start_url = site["start_url"]
    print(f"\n--- [一般Webサイト: {site['site_name']}] 取得開始 ---")

    try:
        await page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
    except Exception as e:
        print(f"  └ アクセス失敗: {e}")
        return []

    soup = BeautifulSoup(await page.content(), "html.parser")
    page_urls = [start_url]

    start_parsed = urlparse(start_url)
    base_domain_path = start_parsed.netloc + start_parsed.path

    for a_tag in soup.find_all("a", href=True):
        full_url = urljoin(start_url, a_tag["href"])
        parsed_url = urlparse(full_url)
        # 同一配下のページのみに限定して収集
        if (parsed_url.netloc + parsed_url.path).startswith(base_domain_path) and full_url not in page_urls:
            page_urls.append(full_url)

    data_list = []
    for index, url in enumerate(page_urls, 1):
        print(f"  [{index}/{len(page_urls)}] 取得中: {url}")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            page_soup = BeautifulSoup(await page.content(), "html.parser")
            
            title = page_soup.find("h1").text.strip() if page_soup.find("h1") else (page_soup.find("title").text.strip() if page_soup.find("title") else "無題")
            body_text = " ".join(page_soup.body.text.split()) if page_soup.body else ""

            data_list.append({"site_name": site["site_name"], "title": title, "url": url, "content": body_text})
        except Exception as e:
            print(f"    └ スキップ: {e}")
    return data_list

# --- 単一ページ用スクレイパー ---
async def scrape_single_page(page, site):
    url = site["url"]
    print(f"\n--- [単一ページ: {site['site_name']}] 取得開始 ---")

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        page_soup = BeautifulSoup(await page.content(), "html.parser")
        title = page_soup.find("title").text.strip() if page_soup.find("title") else site["site_name"]
        body_text = " ".join(page_soup.body.text.split()) if body_shell else "" if not page_soup.body else " ".join(page_soup.body.text.split())

        return [{"site_name": site["site_name"], "title": title, "url": url, "content": body_text}]
    except Exception as e:
        print(f"  └ 取得失敗: {e}")
        return []

# --- メイン処理 ---
async def main():
    async with async_playwright() as p:
        print("ブラウザを起動しています...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        all_search_data = []

        for site in TARGET_SITES:
            stype = site["type"]
            if stype == "atwiki":
                data = await scrape_atwiki(page, site)
            elif stype == "google_sites":
                data = await scrape_google_sites(page, site)
            elif stype == "generic":
                data = await scrape_generic(page, site)
            elif stype == "single_page":
                data = await scrape_single_page(page, site)
            else:
                continue

            all_search_data.extend(data)

        for idx, item in enumerate(all_search_data, 1):
            item["id"] = idx

        tokyo_tz = zoneinfo.ZoneInfo("Asia/Tokyo")
        now_tokyo = datetime.now(tokyo_tz).strftime("%Y年%m月%d日 %H:%M:%S")

        output_payload = {
            "last_updated": now_tokyo,
            "items": all_search_data
        }

        output_file = "search_index.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_payload, f, ensure_ascii=False, indent=2)

        print(f"\n✨ 全サイト完了！ [{now_tokyo} (JST)] 合計 {len(all_search_data)} 件を `{output_file}` に保存しました。")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
