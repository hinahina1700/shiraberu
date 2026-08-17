import os
import time
import random
import json
from datetime import datetime
import zoneinfo
from urllib.parse import urljoin
import cloudscraper
from bs4 import BeautifulSoup

# --- 設定 ---
WIKI_ID = "nanahamakoku"
SAVE_DIR = "wiki_backup_step"
SAVE_TEXT = True
SAVE_HTML = True

OTHER_SITES = [
    {"site_name": "キリッペのお部屋", "type": "google_sites", "url": "https://sites.google.com/view/kirippe/"},
    {"site_name": "KIRIPE公式サイト", "type": "google_sites", "url": "https://sites.google.com/view/kiripe/"},
    {"site_name": "霞野タウン", "type": "google_sites", "url": "https://sites.google.com/view/kasumino-town/"},
    {"site_name": "KIRIPE公式サイト", "type": "generic", "url": "https://kiripe.tomidare.tokyo/"},
    {"site_name": "霞野タウン", "type": "generic", "url": "https://town.tomidare.tokyo/"},
    {"site_name": "キリッペのお部屋", "type": "generic", "url": "https://kirippe.tomidare.tokyo/"},
    {"site_name": "日原日報", "type": "generic", "url": "https://awafgs.github.io/hihara_news/"},
    {"site_name": "日原フロンティア", "type": "generic", "url": "https://awafgs.github.io/Frontier_Building/"},
    {"site_name": "nullpo乗換案内", "type": "single_page", "url": "https://tomidare1234.github.io/nullpo_norikaeannai/"},
    {"site_name": "WARO航空案内", "type": "single_page", "url": "https://awafgs.github.io/NanahamaAirplaneInfo/"},
]

# フォルダ作成
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)
if SAVE_TEXT:
    os.makedirs(os.path.join(SAVE_DIR, "text"), exist_ok=True)
if SAVE_HTML:
    os.makedirs(os.path.join(SAVE_DIR, "html"), exist_ok=True)

# Cloudflare対策用スクレイパーの作成
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)

all_collected_items = []
total_images_count = 0

def process_and_save(soup, title_text, target_url, site_name, page_id_str):
    for tag in soup.select('script, style, iframe, .adsbygoogle, div[id^="ad_"], .atwiki-ad'):
        tag.decompose()

    content_tag = soup.find(id='wikibody') or soup.find(id='atwiki-body') or soup.find('body')
    if not content_tag:
        return None

    images = []
    for img in soup.find_all("img", src=True):
        src = img["src"]
        if not src or src.startswith("data:") or src.lower().endswith((".svg", ".ico", ".gif", ".png?")) or "pixel" in src.lower():
            continue
        full_img_url = urljoin(target_url, src)
        if not any(item["src"] == full_img_url for item in images):
            alt_text = img.get("alt", "").strip() or img.get("title", "").strip() or "ページ画像"
            images.append({"src": full_img_url, "alt": alt_text})

    body_text = " ".join(content_tag.text.split())
    safe_title = title_text.translate(str.maketrans('/\\:*?"<>|', '_________'))

    def make_path(folder, ext):
        base = os.path.join(SAVE_DIR, folder, f"{safe_title}{ext}")
        if not os.path.exists(base):
            return base
        return os.path.join(SAVE_DIR, folder, f"{safe_title}_{page_id_str}{ext}")

    if SAVE_TEXT:
        lines = [line.strip() for line in content_tag.get_text().splitlines() if line.strip()]
        txt_path = make_path("text", ".txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    if SAVE_HTML:
        html_content = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>{title_text}</title>
</head>
<body>
  <h1>{title_text}</h1>
  <p>出典: <a href="{target_url}">{target_url}</a></p>
  <hr>
  {content_tag.decode_contents()}
</body>
</html>"""
        html_path = make_path("html", ".html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

    return {
        "site_name": site_name,
        "title": title_text,
        "url": target_url,
        "content": body_text,
        "images": images[:20]
    }

def get_atwiki_page_list(wiki_id):
    """atwikiの全ページ一覧からURLを全件自動抽出する（2ページ目以降も確実に巡回）"""
    print("📋 atwikiの全ページ一覧（URL）を取得中...")
    page_urls = set()
    page_num = 1

    while True:
        list_url = f"https://w.atwiki.jp/{wiki_id}/list?page={page_num}"
        try:
            res = scraper.get(list_url, timeout=10)
            if res.status_code != 200:
                break

            res.encoding = res.apparent_encoding
            soup = BeautifulSoup(res.text, 'html.parser')

            # ページ一覧リンクを抽出
            links = soup.select('div.atwiki-content ul li a, #wikibody ul li a')
            found_in_page = 0

            for link in links:
                href = link.get('href', '')
                if href and f'/{wiki_id}/pages/' in href and href.endswith('.html'):
                    full_url = urljoin(list_url, href)
                    if full_url not in page_urls:
                        page_urls.add(full_url)
                        found_in_page += 1

            # このページに新しいリンクが一つもなければ終了
            if found_in_page == 0:
                break

            print(f"  📄 一覧ページ {page_num}: {found_in_page} 件のURLを発見（累計: {len(page_urls)} 件）")
            page_num += 1
            # 元の早いテンポを維持（0.3秒〜0.8秒）
            time.sleep(random.uniform(0.3, 0.8))

        except Exception as e:
            print(f"  ❌ 一覧取得エラー: {e}")
            break

    return list(page_urls)

print("========================================")
print(" 🚀 高速・全ページ網羅 データ収集ツール開始")
print("========================================")

# --- 1. 七浜国wikiのURL一覧取得 ＆ 巡回 ---
wiki_urls = get_atwiki_page_list(WIKI_ID)

if not wiki_urls:
    print("⚠️ ページ一覧が自動取得できなかったため、基本ページリストを作成します。")
    wiki_urls = [f"https://w.atwiki.jp/{WIKI_ID}/pages/{i}.html" for i in range(1, 651)]

print(f"\n--- 七浜国wiki 巡回開始 (全 {len(wiki_urls)} ページ) ---")

for idx, target_url in enumerate(wiki_urls, 1):
    try:
        res = scraper.get(target_url, timeout=10)

        if res.status_code == 403:
            print(f"  ❌ [{idx}/{len(wiki_urls)}] 403ブロック: {target_url}")
            continue
        elif res.status_code != 200:
            continue

        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')

        if "お探しのページ" in res.text or "存在しません" in res.text:
            continue

        title_tag = soup.find('h2', id='page_title') or soup.find('h1')
        title_text = title_tag.text.strip() if title_tag else f"七浜国wiki ページ {idx}"

        item_data = process_and_save(soup, title_text, target_url, "七浜国wiki", str(idx))
        if item_data:
            all_collected_items.append(item_data)
            total_images_count += len(item_data["images"])
            print(f"  ✅ [{idx}/{len(wiki_urls)}] 取得成功: {title_text}")

    except Exception as e:
        print(f"  ❌ エラー ({target_url}): {e}")

    # 元の高速テンポを維持（0.5秒〜1.0秒）
    time.sleep(random.uniform(0.5, 1.0))

# --- 2. その他サイトの巡回 ---
print(f"\n--- その他サイトの巡回開始 ---")
for idx, site in enumerate(OTHER_SITES, 1):
    target_url = site["url"]
    site_name = site["site_name"]
    print(f"アクセス中: {site_name} ({target_url})")

    try:
        res = scraper.get(target_url, timeout=10)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')

        title_tag = soup.find('h1') or soup.find('title')
        title_text = title_tag.text.strip().split(' - ')[0].strip() if title_tag else site_name

        item_data = process_and_save(soup, title_text, target_url, site_name, f"other_{idx}")
        if item_data:
            all_collected_items.append(item_data)
            total_images_count += len(item_data["images"])
            print(f"  ✅ 取得成功: {title_text}")
    except Exception as e:
        print(f"  ❌ エラー: {e}")
    
    time.sleep(random.uniform(0.5, 1.0))

# --- search_index.json 保存 ---
for idx, item in enumerate(all_collected_items, 1):
    item["id"] = idx

tokyo_tz = zoneinfo.ZoneInfo("Asia/Tokyo")
now_tokyo = datetime.now(tokyo_tz).strftime("%Y年%m月%d日 %H:%M:%S")

output_payload = {
    "last_updated": now_tokyo,
    "items": all_collected_items,
}

with open("search_index.json", "w", encoding="utf-8") as f:
    json.dump(output_payload, f, ensure_ascii=False, indent=2)

print(f"\n========================================")
print(f" 🎉 処理完了！収集できた件数: {len(all_collected_items)} 件")
print(f" 📂 search_index.json を無事に作成しました！")
print(f"========================================")
