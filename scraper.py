import asyncio
import json
import random
import zoneinfo
from datetime import datetime
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# --- 設定 ---
WIKI_ID = "nanahamakoku"
MAX_PAGE = 650

# 対象サイト定義
OTHER_SITES = [
    {"site_name": "キリッペのお部屋", "type": "google_sites", "base_url": "https://sites.google.com/view/kirippe/"},
    {"site_name": "KIRIPE公式サイト", "type": "google_sites", "base_url": "https://sites.google.com/view/kiripe/"},
    {"site_name": "霞野タウン", "type": "google_sites", "base_url": "https://sites.google.com/view/kasumino-town/"},
    {"site_name": "KIRIPE公式サイト", "type": "generic", "start_url": "https://kiripe.tomidare.tokyo/"},
    {"site_name": "霞野タウン", "type": "generic", "start_url": "https://town.tomidare.tokyo/"},
    {"site_name": "キリッペのお部屋", "type": "generic", "start_url": "https://kirippe.tomidare.tokyo/"},
    {"site_name": "日原日報", "type": "generic", "start_url": "https://awafgs.github.io/hihara_news/"},
    {"site_name": "日原フロンティア", "type": "generic", "start_url": "https://awafgs.github.io/Frontier_Building/"},
    {"site_name": "nullpo乗換案内", "type": "single_page", "url": "https://tomidare1234.github.io/nullpo_norikaeannai/"},
    {"site_name": "WARO航空案内", "type": "single_page", "url": "https://awafgs.github.io/NanahamaAirplaneInfo/"},
]

def extract_images(soup, base_url):
    """ページ内の画像を高精度に抽出"""
    images = []
    for img in soup.find_all("img", src=True):
        src = img["src"]
        if not src or src.startswith("data:") or src.lower().endswith((".svg", ".ico", ".gif", ".png?")) or "pixel" in src.lower():
            continue
        full_img_url = urljoin(base_url, src)
        if not any(item["src"] == full_img_url for item in images):
            alt_text = img.get("alt", "").strip() or img.get("title", "").strip() or "ページ画像"
            images.append({"src": full_img_url, "alt": alt_text})
    return images[:20]

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
        )
        
        page = await context.new_page()
        stealth = Stealth()
        await stealth.apply_stealth_async(page)
        
        all_data = []
        total_images_count = 0

        # 1. 七浜国wikiを1ページずつ総当たり取得
        print(f"========================================")
        print(f" 七浜国wiki 総当たり開始 (1 ~ {MAX_PAGE} ページ)")
        print(f"========================================")
        
        for page_num in range(1, MAX_PAGE + 1):
            url = f"https://w.atwiki.jp/{WIKI_ID}/pages/{page_num}.html"
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=12000)
                if response is None or response.status >= 400:
                    continue

                content = await page.content()
                if "お探しのページは見つかりませんでした" in content or "ページがありません" in content:
                    continue
                
                soup = BeautifulSoup(content, "html.parser")
                title_elem = soup.find("h2", id="page_title")
                title = title_elem.text.strip() if title_elem else "無題"
                
                body_elem = soup.find("div", id="wikibody") or soup.find("div", id="atwiki-body") or soup.find("body")
                body = " ".join(body_elem.text.split()) if body_elem else ""
                
                if len(body) < 10:
                    continue

                images = extract_images(soup, url)
                total_images_count += len(images)

                item = {
                    "site_name": "七浜国wiki",
                    "title": title,
                    "url": url,
                    "content": body,
                    "images": images
                }
                all_data.append(item)
                
                # リアルタイムで取得したページ情報を表示
                print(f"  ✅ [七浜国wiki] ページ {page_num} 取得: {title} ({url}) [画像: {len(images)}枚]")
                
                await asyncio.sleep(0.1)
                
            except Exception:
                continue

        print(f"\n✨ 七浜国wiki完了！ 有効データ数: {len(all_data)}件\n")

        # 2. その他サイトを巡回
        print(f"========================================")
        print(f" その他サイトの巡回を開始します")
        print(f"========================================")
        
        for site in OTHER_SITES:
            print(f"--- [巡回中] {site['site_name']} ---")
            try:
                target_url = site.get("base_url") or site.get("start_url") or site.get("url")
                await page.goto(target_url, timeout=30000)
                await asyncio.sleep(1.0)
                content = await page.content()
                soup = BeautifulSoup(content, "html.parser")
                title = soup.title.string.strip() if soup.title and soup.title.string else site["site_name"]
                body = " ".join(soup.body.text.split()) if soup.body else ""
                
                images = extract_images(soup, target_url)
                total_images_count += len(images)

                item = {
                    "site_name": site["site_name"],
                    "title": title,
                    "url": page.url,
                    "content": body,
                    "images": images
                }
                all_data.append(item)
                print(f"  ✅ 取得成功: {title} ({page.url}) [画像: {len(images)}枚]")
            except Exception as e:
                print(f"  ❌ 取得失敗: {e}")

        # IDを順番に付与
        for idx, item in enumerate(all_data, 1):
            item["id"] = idx

        # 保存
        tokyo_tz = zoneinfo.ZoneInfo("Asia/Tokyo")
        now_tokyo = datetime.now(tokyo_tz).strftime("%Y年%m月%d日 %H:%M:%S")
        
        output_payload = {
            "last_updated": now_tokyo,
            "items": all_data,
        }

        output_file = "search_index.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_payload, f, ensure_ascii=False, indent=2)

        print(f"\n========================================")
        print(f" 🎉 すべての処理が完了しました！")
        print(f" 📂 保存ファイル: `{output_file}`")
        print(f" 📄 合計出力ページ数 (サイト数): {len(all_data)} 件")
        print(f" 🖼️ 合計抽出画像数: {total_images_count} 枚")
        print(f"========================================")
        
        await browser.close()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
