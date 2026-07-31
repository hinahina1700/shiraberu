import asyncio
import json
import os
import random
import re
import zoneinfo
from datetime import datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from google import genai
from playwright.async_api import async_playwright

# ==========================================
# 1. Gemini API クライアントの設定
# ==========================================
API_KEY = os.environ.get("GEMINI_API_KEY")

gemini_client = None
if API_KEY:
    try:
        gemini_client = genai.Client(api_key=API_KEY)
        print("✅ Gemini API クライアントの初期化に成功しました。")
    except Exception as e:
        print(f"⚠️ Gemini API クライアントの初期化に失敗しました: {e}")
else:
    print(
        "ℹ️ GEMINI_API_KEY が設定されていないため、AI要約の生成は本文抜粋機能にフォールバックします。"
    )


def clean_url(url):
    """URLから `#` 以降のハッシュ（アンカー）を除去して重複を防ぐ"""
    if not url:
        return ""
    return url.split("#")[0]


async def generate_ai_summary(title, content):
    """Gemini API（gemini-2.5-flash）を使って要約を生成。エラー時は本文抜粋を返す"""
    cleaned_content = " ".join(content.split()) if content else ""

    if len(cleaned_content) < 30:
        return cleaned_content if cleaned_content else f"{title}に関するページです。"

    if not gemini_client:
        return cleaned_content[:140] + ("..." if len(cleaned_content) > 140 else "")

    prompt = f"""
以下のWebページの内容を読み、対話型AI検索エンジン（Google AI Overview風）の回答として適切な、分かりやすい要約・解説（100文字〜150文字程度）を作成してください。

【ページタイトル】: {title}
【本文】:
{cleaned_content[:1500]}
"""

    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            ),
        )
        summary = response.text.strip()
        await asyncio.sleep(0.8)  # レート制限対策
        return summary
    except Exception as e:
        print(f"  ⚠️ AI要約の生成失敗 ({title}): {e}")
        return cleaned_content[:140] + ("..." if len(cleaned_content) > 140 else "")


def extract_images(soup, base_url):
    """【精度向上】アイキャッチ(OGP)および本文中の主要画像を高品質に抽出"""
    images = []

    # 1. OGP画像（アイキャッチ）があれば最優先で追加
    for prop in ["og:image", "twitter:image"]:
        og_tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        if og_tag and og_tag.get("content"):
            og_url = clean_url(urljoin(base_url, og_tag["content"]))
            if og_url and not any(item["src"] == og_url for item in images):
                images.append({"src": og_url, "alt": "アイキャッチ画像"})
                break

    # ノイズになりやすいエリアを除外
    soup_copy = BeautifulSoup(str(soup), "html.parser")
    for noisy in soup_copy.select("header, footer, nav, .header, .footer, .nav, .sidebar, #sidebar, .comment, script, style, form"):
        noisy.decompose()

    # 2. 本文エリアの画像を高精度に取得
    for img in soup_copy.find_all("img", src=True):
        src = img["src"]
        if not src or src.startswith("data:") or src.lower().endswith((".svg", ".ico", ".gif", ".png")):
            # 小さなアイコンやボタン等の拡張子・データURIを除外
            if src.lower().endswith((".svg", ".ico", ".gif")):
                continue

        full_img_url = clean_url(urljoin(base_url, src))

        # 不要なサムネイルやアイコン・ボタンのキーワードフィルタ
        ng_keywords = ["logo", "icon", "banner", "btn", "button", "avatar", "common", "favicon", "parts", "spacer"]
        if any(ng in full_img_url.lower() for ng in ng_keywords):
            continue

        if not any(item["src"] == full_img_url for item in images):
            alt_text = img.get("alt", "").strip() or "ページ画像"
            images.append({"src": full_img_url, "alt": alt_text})

    return images[:15]


async def random_delay(min_sec=2.0, max_sec=4.0):
    wait_time = random.uniform(min_sec, max_sec)
    print(f"       ⏳ {wait_time:.2f} 秒待機中...")
    await asyncio.sleep(wait_time)


TARGET_SITES = [
    {
        "site_name": "七浜国wiki",
        "type": "atwiki",
        "wiki_id": "nanahamakoku",
    },
    {
        "site_name": "キリッペのお部屋",
        "type": "google_sites",
        "base_url": "https://sites.google.com/view/kirippe/",
    },
    {
        "site_name": "KIRIPE公式サイト",
        "type": "google_sites",
        "base_url": "https://sites.google.com/view/kiripe/",
    },
    {
        "site_name": "霞野タウン",
        "type": "google_sites",
        "base_url": "https://sites.google.com/view/kasumino-town/",
    },
    {
        "site_name": "KIRIPE公式サイト",
        "type": "generic",
        "start_url": "https://kiripe.tomidare.tokyo/",
    },
    {
        "site_name": "霞野タウン",
        "type": "generic",
        "start_url": "https://town.tomidare.tokyo/",
    },
    {
        "site_name": "キリッペのお部屋",
        "type": "generic",
        "start_url": "https://kirippe.tomidare.tokyo/",
    },
    {
        "site_name": "日原日報",
        "type": "generic",
        "start_url": "https://awafgs.github.io/hihara_news/",
    },
    {
        "site_name": "日原フロンティア",
        "type": "generic",
        "start_url": "https://awafgs.github.io/Frontier_Building/",
    },
    {
        "site_name": "nullpo乗換案内",
        "type": "single_page",
        "url": "https://tomidare1234.github.io/nullpo_norikaeannai/",
    },
    {
        "site_name": "WARO航空案内",
        "type": "single_page",
        "url": "https://awafgs.github.io/NanahamaAirplaneInfo/",
    },
]


async def scrape_atwiki(page, site):
    wiki_id = site["wiki_id"]
    base_url = f"https://w.atwiki.jp/{wiki_id}/"
    list_url = f"{base_url}list"

    print(f"\n--- [atwiki: {site['site_name']}] 取得開始 ---")

    soup = None
    for attempt in range(1, 5):
        try:
            print(f"  一覧を取得中 (試行 {attempt}/4)...")
            await page.goto(list_url, wait_until="networkidle", timeout=60000)
            await random_delay(3.0, 5.0)
            html_content = await page.content()
            
            # しばらくお待ちください（Cloudflare等）対策
            if "しばらくお待ちください" in html_content or "ロボットではありません" in html_content or "Just a moment" in html_content:
                print(f"  ⚠️ ブロック画面を検出。8秒待機して再試行します...")
                await asyncio.sleep(8)
                continue

            soup = BeautifulSoup(html_content, "html.parser")
            if soup.find_all("a", href=True):
                break
        except Exception as e:
            print(f"  └ 失敗: {e}")
            if attempt == 4:
                return []
            await asyncio.sleep(6)

    if not soup:
        return []

    page_urls = []
    for a_tag in soup.find_all("a", href=True):
        full_url = clean_url(urljoin(base_url, a_tag["href"]))
        
        ng_paths = ["/edit", "/diff", "/keyword/", "/cmd/", "/tag/", "/counter/"]
        if any(ng in full_url for ng in ng_paths):
            continue

        if (
            f"/{wiki_id}/pages/" in full_url
            and full_url.endswith(".html")
            and "login.atwiki.jp" not in full_url
        ):
            if full_url not in page_urls:
                page_urls.append(full_url)

    print(f"  対象ページ数: {len(page_urls)} 件")

    data_list = []
    for index, url in enumerate(page_urls, 1):
        print(f"  [{index}/{len(page_urls)}] 取得中: {url}")

        success = False
        for attempt in range(1, 4):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                await random_delay(1.5, 3.0)
                await page.evaluate("window.scrollBy(0, 300);")

                html_content = await page.content()
                if "しばらくお待ちください" in html_content or "ロボットではありません" in html_content or "Just a moment" in html_content:
                    print(f"    └ ブロック画面検出。10秒待機して再試行 ({attempt}/3)")
                    await asyncio.sleep(10)
                    continue

                page_soup = BeautifulSoup(html_content, "html.parser")

                title_elem = page_soup.find("h2", id="page_title")
                title = (
                    title_elem.text.strip()
                    if title_elem
                    else (
                        page_soup.find("title").text.split("-")[0].strip()
                        if page_soup.find("title")
                        else "無題"
                    )
                )

                body_elem = page_soup.find("div", id="wikibody") or page_soup.find("div", id="atwiki-body") or page_soup.find("body")

                if body_elem:
                    for noisy in body_elem.select("script, style, iframe, form, .sidebar, #header, #footer"):
                        noisy.decompose()
                    body_text = " ".join(body_elem.text.split())
                else:
                    body_text = ""

                images = extract_images(page_soup, url)
                ai_summary = await generate_ai_summary(title, body_text)

                tokyo_tz = zoneinfo.ZoneInfo("Asia/Tokyo")
                indexed_at = datetime.now(tokyo_tz).strftime("%Y-%m-%d %H:%M")

                data_list.append({
                    "site_name": site["site_name"],
                    "title": title,
                    "url": url,
                    "content": body_text,
                    "ai_summary": ai_summary,
                    "images": images,
                    "indexed_at": indexed_at
                })
                success = True
                break
            except Exception as e:
                print(f"    └ エラー ({attempt}/3): {e}")
                if attempt < 3:
                    await asyncio.sleep(5)
        if not success:
            print(f"    ❌ ページの取得をスキップしました: {url}")

    return data_list


async def scrape_google_sites(page, site):
    base_url = clean_url(site["base_url"])
    print(f"\n--- [Google Sites: {site['site_name']}] 取得開始 ---")
    try:
        await page.goto(base_url, wait_until="networkidle", timeout=30000)
        await random_delay(2.0, 4.0)
    except Exception as e:
        print(f"  └ アクセス失敗: {e}")
        return []

    soup = BeautifulSoup(await page.content(), "html.parser")
    page_urls = [base_url]
    for a_tag in soup.find_all("a", href=True):
        full_url = clean_url(urljoin(base_url, a_tag["href"]))
        if full_url.startswith(base_url) and full_url not in page_urls:
            page_urls.append(full_url)

    data_list = []
    for index, url in enumerate(page_urls, 1):
        print(f"  [{index}/{len(page_urls)}] 取得中: {url}")
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await random_delay(1.5, 3.0)
            page_soup = BeautifulSoup(await page.content(), "html.parser")
            title = (
                page_soup.find("title").text.strip()
                if page_soup.find("title")
                else "無題"
            )
            body_text = (
                " ".join(page_soup.body.text.split()) if page_soup.body else ""
            )

            ai_summary = await generate_ai_summary(title, body_text)
            tokyo_tz = zoneinfo.ZoneInfo("Asia/Tokyo")
            indexed_at = datetime.now(tokyo_tz).strftime("%Y-%m-%d %H:%M")

            data_list.append({
                "site_name": site["site_name"],
                "title": title,
                "url": url,
                "content": body_text,
                "ai_summary": ai_summary,
                "images": extract_images(page_soup, url),
                "indexed_at": indexed_at
            })
        except Exception as e:
            print(f"    └ スキップ: {e}")
    return data_list


async def scrape_generic(page, site):
    start_url = clean_url(site["start_url"])
    print(f"\n--- [一般Webサイト: {site['site_name']}] 取得開始 ---")
    try:
        await page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
        await random_delay(2.0, 4.0)
    except Exception as e:
        print(f"  └ アクセス失敗: {e}")
        return []

    soup = BeautifulSoup(await page.content(), "html.parser")
    page_urls = [start_url]
    start_parsed = urlparse(start_url)
    base_domain_path = start_parsed.netloc + start_parsed.path

    for a_tag in soup.find_all("a", href=True):
        full_url = clean_url(urljoin(start_url, a_tag["href"]))
        parsed_url = urlparse(full_url)
        if (parsed_url.netloc + parsed_url.path).startswith(
            base_domain_path
        ) and full_url not in page_urls:
            page_urls.append(full_url)

    data_list = []
    for index, url in enumerate(page_urls, 1):
        print(f"  [{index}/{len(page_urls)}] 取得中: {url}")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await random_delay(1.5, 3.0)
            page_soup = BeautifulSoup(await page.content(), "html.parser")
            title = (
                page_soup.find("h1").text.strip()
                if page_soup.find("h1")
                else (
                    page_soup.find("title").text.strip()
                    if page_soup.find("title")
                    else "無題"
                )
            )
            body_text = (
                " ".join(page_soup.body.text.split()) if page_soup.body else ""
            )

            ai_summary = await generate_ai_summary(title, body_text)
            tokyo_tz = zoneinfo.ZoneInfo("Asia/Tokyo")
            indexed_at = datetime.now(tokyo_tz).strftime("%Y-%m-%d %H:%M")

            data_list.append({
                "site_name": site["site_name"],
                "title": title,
                "url": url,
                "content": body_text,
                "ai_summary": ai_summary,
                "images": extract_images(page_soup, url),
                "indexed_at": indexed_at
            })
        except Exception as e:
            print(f"    └ スキップ: {e}")
    return data_list


async def scrape_single_page(page, site):
    url = clean_url(site.get("url") or site.get("start_url"))
    print(f"\n--- [単一ページ: {site['site_name']}] 取得開始 ---")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await random_delay(2.0, 3.0)
        page_soup = BeautifulSoup(await page.content(), "html.parser")
        title = (
            page_soup.find("title").text.strip()
            if page_soup.find("title")
            else site["site_name"]
        )
        body_text = (
            " ".join(page_soup.body.text.split()) if page_soup.body else ""
        )

        ai_summary = await generate_ai_summary(title, body_text)
        tokyo_tz = zoneinfo.ZoneInfo("Asia/Tokyo")
        indexed_at = datetime.now(tokyo_tz).strftime("%Y-%m-%d %H:%M")

        return [{
            "site_name": site["site_name"],
            "title": title,
            "url": url,
            "content": body_text,
            "ai_summary": ai_summary,
            "images": extract_images(page_soup, url),
            "indexed_at": indexed_at
        }]
    except Exception as e:
        print(f"  └ 取得失敗: {e}")
        return []


async def main():
    async with async_playwright() as p:
        print("ブラウザを起動しています...")
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="ja-JP",
        )
        page = await context.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.navigator.chrome = { runtime: {} };
        """)

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
            "items": all_search_data,
        }

        output_file = "search_index.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_payload, f, ensure_ascii=False, indent=2)

        print(
            f"\n✨ 全サイト完了！ [{now_tokyo} (JST)] 合計 {len(all_search_data)} 件を `{output_file}` に保存しました。"
        )
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
