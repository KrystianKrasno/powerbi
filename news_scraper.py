import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
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
    r'\s+\d{1,2},?\s+\d{4}\b', flags=re.IGNORECASE
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

def extract_release_links_by_date(soup, limit=10):
    """
    ORIGINAL METHOD - Finds release links based on date nodes.
    """
    results = []
    seen = set()
    text_nodes = soup.find_all(string=DATE_RE)

    print(f"[Method 1] Found {len(text_nodes)} date text nodes")

    for node in text_nodes:
        date_match = DATE_RE.search(node)
        if not date_match:
            continue
        date_text = date_match.group(0).strip()
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
            if not title or len(title) < 5:  # Lowered from 8
                h = parent.find(['h1','h2','h3','h4'])
                if h:
                    title = h.get_text(" ", strip=True)
            if not title or len(title) < 5:  # Lowered from 8
                continue
            seen.add(full)
            print(f"  ✓ {date_text} - {title[:70]}...")
            results.append((date_text, title, full))
            if len(results) >= limit:
                break
    return results, seen

def extract_all_release_links(soup, seen_urls, limit=10):
    """
    BACKUP METHOD - Find all links matching /releases/ pattern.
    Much more lenient filtering.
    """
    results = []
    
    # Find all links with /releases/ in href
    all_links = soup.find_all('a', href=re.compile(r'/releases/(2024|2025)/'))
    print(f"[Method 2] Found {len(all_links)} /releases/ links for 2024-2025")
    
    checked = 0
    for link in all_links:
        if len(results) >= limit:
            break
            
        href = link.get('href', '').strip()
        if not href:
            continue
            
        full_url = norm_url(href)
        
        # Skip if already found
        if full_url in seen_urls:
            continue
        
        checked += 1
        
        # Get title - be very lenient
        title = link.get_text(" ", strip=True)
        
        # If link text is empty or too short, look in parent
        if not title or len(title) < 5:
            parent = link.parent
            # Check the parent's text
            if parent:
                parent_text = parent.get_text(" ", strip=True)
                # Remove the link's own text to see what else is there
                if parent_text and len(parent_text) > len(title):
                    title = parent_text
        
        # Still too short? Look for ANY nearby heading
        if not title or len(title) < 5:
            parent = link.parent
            for _ in range(4):  # Increased from 3
                if parent:
                    heading = parent.find(['h1','h2','h3','h4','h5','h6','strong','b'])
                    if heading:
                        potential_title = heading.get_text(" ", strip=True)
                        if len(potential_title) >= 5:
                            title = potential_title
                            break
                    parent = parent.parent
        
        # Last resort: use the URL slug as title
        if not title or len(title) < 5:
            # Extract from URL like /releases/2024/some-article-name.html
            url_parts = full_url.split('/')
            if len(url_parts) > 0:
                slug = url_parts[-1].replace('.html', '').replace('-', ' ').title()
                if len(slug) >= 5:
                    title = slug
        
        if not title or len(title) < 5:
            print(f"    ✗ Skipped (no title): {full_url}")
            continue
        
        # Try to find date
        date_text = "Recent"
        parent = link.parent
        for _ in range(4):
            if parent:
                date_match = DATE_RE.search(parent.get_text())
                if date_match:
                    date_text = date_match.group(0).strip()
                    break
                parent = parent.parent
        
        seen_urls.add(full_url)
        print(f"  ✓ {date_text} - {title[:70]}...")
        results.append((date_text, title, full_url))
    
    print(f"[Method 2] Checked {checked} links, found {len(results)} valid articles")
    return results

def fetch_toyota_news(limit=5):
    """Scrapes Toyota Media Site and returns JSON-ready dict."""
    print(f"Fetching from: {LIST_URL}")
    r = requests.get(LIST_URL, timeout=15, headers=HEADERS)
    r.raise_for_status()
    print(f"Status: {r.status_code}, Content length: {len(r.text)} bytes")
    
    soup = BeautifulSoup(r.text, "html.parser")

    # Method 1: Original date-based approach
    print("\n--- Method 1: Date-based search ---")
    article_links, seen_urls = extract_release_links_by_date(soup, limit=limit)
    
    # Method 2: If we need more articles, use broader search
    if len(article_links) < limit:
        print(f"\n--- Method 2: Need {limit - len(article_links)} more articles ---")
        additional = extract_all_release_links(soup, seen_urls, limit - len(article_links))
        article_links.extend(additional)
    
    print(f"\n=== Total: {len(article_links)} articles ===\n")
    
    if not article_links:
        print("⚠ WARNING: No articles found!")
        # Save HTML for debugging
        with open("debug_page.html", "w", encoding="utf-8") as f:
            f.write(r.text)
        print("Saved HTML to debug_page.html")
    
    # Fetch details
    items = []
    for idx, (date_text, title, url) in enumerate(article_links, 1):
        print(f"[{idx}/{len(article_links)}] Fetching: {url}")
        img_url, desc = fetch_article_details(url)
        items.append({
            "date": date_text,
            "title": title,
            "description": desc[:600] if desc else "",
            "image_url": img_url,
            "url": url
        })
    
    return {
        "source": "Toyota Canada Media",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "articles": items
    }

def main():
    try:
        print("=" * 70)
        print("TOYOTA CANADA NEWS SCRAPER")
        print("=" * 70)
        
        news_data = fetch_toyota_news(limit=5)
        
        os.makedirs("powerbi", exist_ok=True)
        
        output_path = "powerbi/toyota_news.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(news_data, f, ensure_ascii=False, indent=2)
        
        print("\n" + "=" * 70)
        print(f"✓ SUCCESS: {len(news_data['articles'])} articles saved")
        print("=" * 70)
        
        if news_data['articles']:
            print("\nArticles:")
            for idx, article in enumerate(news_data['articles'], 1):
                print(f"  {idx}. [{article['date']}] {article['title'][:65]}...")
        else:
            print("\n⚠ No articles found")
        
        print("\n" + "=" * 70)
        sys.exit(0)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        traceback.print_exc()
        sys.exit(2)

if __name__ == "__main__":
    main()