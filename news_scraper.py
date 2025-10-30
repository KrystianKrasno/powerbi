import requests
from bs4 import BeautifulSoup, NavigableString
from datetime import datetime
import json
import re
import sys
import traceback
import os

BASE_URL = "https://media.toyota.ca"
LIST_URL = f"{BASE_URL}/en/corporateinewsrelease.html"
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

DATE_RE = re.compile(
    r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
    r'Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
    r'\s+\d{1,2},\s+\d{4}\b', flags=re.IGNORECASE
)

def norm_url(href):
    href = href.strip()
    if href.startswith('//'):
        return 'https:' + href
    if href.startswith('/'):
        return BASE_URL + href
    if href.startswith('http'):
        return href
    return BASE_URL + '/' + href

def fetch_article_details(url):
    """Extracts image and description from article detail page."""
    try:
        r = requests.get(url, timeout=15, headers=HEADERS)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Prefer og:image
        img_url = ""
        meta_og = soup.find('meta', property='og:image')
        if meta_og and meta_og.get('content'):
            img_url = meta_og['content'].strip()

        # Fallback
        if not img_url:
            img = soup.select_one('article img, .release img, img')
            if img and img.get('src'):
                img_url = img['src'].strip()
        if img_url:
            img_url = norm_url(img_url)

        # Description
        desc = ""
        candidates = (soup.select('article p') or
                      soup.select('.entry-content p') or
                      soup.select('.release p') or
                      soup.find_all('p'))
        for p in candidates:
            txt = p.get_text(" ", strip=True)
            if len(txt) >= 60:
                desc = txt
                break
        if not desc:
            for p in candidates:
                txt = p.get_text(" ", strip=True)
                if txt:
                    desc = txt
                    break
        return img_url or "", desc or ""
    except Exception as e:
        print(f"Warning: Failed to fetch details from {url}: {e}")
        return "", ""

def extract_release_links_by_date(soup, limit=5):
    """Finds the top n release links based on date nodes."""
    results = []
    seen = set()
    text_nodes = soup.find_all(string=DATE_RE)

    print(f"Found {len(text_nodes)} date nodes")

    for node in text_nodes:
        date_text = DATE_RE.search(node).group(0).strip()
        parent = node.parent
        link = None

        # Look for valid link near date
        if parent:
            link = parent.find('a', href=True)
        if not link:
            nxt = parent
            steps = 0
            while nxt and steps < 6:
                nxt = nxt.find_next()
                if nxt and nxt.name == 'a' and nxt.get('href'):
                    link = nxt
                    break
                steps += 1
        if not link and parent and parent.parent:
            link = parent.parent.find('a', href=True)

        if link:
            href = link.get('href').strip()
            full = norm_url(href)
            if full in seen:
                continue
            title = link.get_text(" ", strip=True)
            if not title or len(title) < 8:
                h = parent.find(['h1','h2','h3','h4'])
                if h:
                    title = h.get_text(" ", strip=True)
            if not title or len(title) < 8:
                continue
            seen.add(full)
            print(f"Found article: {date_text} - {title[:50]}...")
            results.append((date_text, title, full))
            if len(results) >= limit:
                break
    return results

def fetch_toyota_news(limit=2):
    """Scrapes Toyota Media Site and returns JSON-ready dict."""
    print(f"Fetching news from {LIST_URL}")
    r = requests.get(LIST_URL, timeout=15, headers=HEADERS)
    r.raise_for_status()
    print(f"Status code: {r.status_code}")
    
    soup = BeautifulSoup(r.text, "html.parser")

    date_links = extract_release_links_by_date(soup, limit)
    
    if not date_links:
        print("WARNING: No articles found on the page")
    
    items = []
    for date_text, title, url in date_links:
        print(f"Fetching details for: {url}")
        img_url, desc = fetch_article_details(url)
        items.append({
            "date": date_text,
            "title": title,
            "description": desc[:600],
            "image_url": img_url,
            "url": url
        })
    
    return {
        "source": "Toyota Canada Media",
        "fetched_at": datetime.utcnow().isoformat(),
        "articles": items
    }

def main():
    try:
        print("Starting Toyota news scraper...")
        news_data = fetch_toyota_news(limit=2)
        
        # Create directory if it doesn't exist
        os.makedirs("powerbi", exist_ok=True)
        
        # Write JSON file
        output_path = "powerbi/toyota_news.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(news_data, f, ensure_ascii=False, indent=2)
        
        print(f"✓ Successfully wrote {len(news_data['articles'])} articles to {output_path}")
        
        # Exit with success even if no articles found (to avoid breaking the workflow)
        if len(news_data['articles']) == 0:
            print("WARNING: No articles were scraped, but JSON file was created")
            sys.exit(0)
        
        sys.exit(0)
        
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Network request failed: {e}")
        traceback.print_exc()
        sys.exit(2)
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}")
        traceback.print_exc()
        sys.exit(2)

if __name__ == "__main__":
    main()