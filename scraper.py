import asyncio
import json
from datetime import datetime
import zoneinfo
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# 設定
WIKI_ID = "nanahamakoku"
BASE_URL = f"https://w.atwiki.jp/{WIKI_ID}/"
LIST_URL = f"{BASE_URL}list"

async def build_search_index():
    async with async_playwright() as p:
        print("ブラウザを起動しています...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # 1. ページ一覧（/list）から全ページのURLを取得
        print(f"ページ一覧を取得中: {LIST_URL}")
        await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)

        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        page_urls = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            full_url = urljoin(BASE_URL, href)

            if (f"/{WIKI_ID}/pages/" in full_url and 
                full_url.endswith(".html") and 
                "login.atwiki.jp" not in full_url):
                if full_url not in page_urls:
                    page_urls.append(full_url)

        print(f"対象Wiki内の有効なページ: 全 {len(page_urls)} 件が見つかりました。\n")

        # 2. 各ページを巡回して本文を収集
        search_data = []

        for index, url in enumerate(page_urls, 1):
            print(f"[{index}/{len(page_urls)}] 取得中: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)

                page_html = await page.content()
                page_soup = BeautifulSoup(page_html, "html.parser")

                title_elem = page_soup.find("h2", id="page_title")
                if title_elem:
                    title = title_elem.text.strip()
                else:
                    raw_title = page_soup.find("title").text if page_soup.find("title") else "タイトル不明"
                    title = raw_title.split("-")[0].strip()

                body_elem = page_soup.find("div", id="wikibody") or page_soup.find("div", id="atwiki-body")
                body_text = " ".join(body_elem.text.split()) if body_elem else ""

                search_data.append({
                    "id": index,
                    "title": title,
                    "url": url,
                    "content": body_text
                })

            except Exception as e:
                print(f"  └ 取得スキップ (エラー): {e}")

        # 日本時間 (Asia/Tokyo) の日時を取得
        tokyo_tz = zoneinfo.ZoneInfo("Asia/Tokyo")
        now_tokyo = datetime.now(tokyo_tz).strftime("%Y年%m月%d日 %H:%M:%S")

        output_payload = {
            "last_updated": now_tokyo,
            "items": search_data
        }

        # JSONファイルに書き出し
        output_file = "search_index.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_payload, f, ensure_ascii=False, indent=2)

        print(f"\n✨ 完了！ [{now_tokyo} (JST)] 時点のデータ（{len(search_data)}件）を `{output_file}` に保存しました。")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(build_search_index())
