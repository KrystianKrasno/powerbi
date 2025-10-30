import requests
from bs4 import BeautifulSoup
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
    r'\s+\d{1,2},?\s+\d{4}\b', flags=re.IGNORECASE
)

def norm_url(href):
    """Normalize URLs to full absolute URLs."""
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

        # Fallback to first image in article
        if not img_url:
            img = soup.select_one('article img, .release img, img')
            if img and img.get('src'):
                img_url = img['src'].strip()
        if img_url:
            img_url = norm_url(img_url)

        # Description - get first substantial paragraph
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

def extract_articles_from_page(soup, limit=5):
    """
    Extract article links from Toyota Canada media page.
    Looks for all <a> tags with href matching /releases/YEAR/
    """
    results = []
    seen_urls = set()
    
    # Find all links that match the release pattern
    all_links = soup.find_all('a', href=re.compile(r'/releases/(2024|2025)/'))
    
    print(f"Found {len(all_links)} potential article links")
    
    for link in all_links:
        if len(results) >= limit:
            break
            
        href = link.get('href', '').strip()
        if not href:
            continue
        
        # Normalize URL
        full_url = norm_url(href)
        
        # Skip duplicates
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        
        # Get title from link text
        title = link.get_text(" ", strip=True)
        
        # If title is too short, look for nearby heading
        if not title or len(title) < 15:
            parent = link.parent
            for _ in range(3):  # Check up to 3 parent levels
                if parent:
                    heading = parent.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                    if heading:
                        title = heading.get_text(" ", strip=True)
                        if len(title) >= 15:
                            break
                    parent = parent.parent
        
        # Skip if still no good title
        if not title or len(title) < 15:
            continue
        
        # Try to find date near the link
        date_text = "Recent"
        parent = link.parent
        for _ in range(4):  # Check up to 4 parent levels for date
            if parent:
                parent_text = parent.get_text()
                date_match = DATE_RE.search(parent_text)
                if date_match:
                    date_text = date_match.group(0).strip().upper()
                    break
                parent = parent.parent
        
        print(f"Found: {date_text} - {title[:70]}...")
        results.append((date_text, title, full_url))
    
    return results

def fetch_toyota_news(limit=5):
    """Scrapes Toyota Media Site and returns JSON-ready dict."""
    print(f"Fetching news from {LIST_URL}")
    
    try:
        r = requests.get(LIST_URL, timeout=15, headers=HEADERS)
        r.raise_for_status()
        print(f"Status code: {r.status_code}")
    except requests.RequestException as e:
        print(f"ERROR: Failed to fetch page: {e}")
        raise
    
    soup = BeautifulSoup(r.text, "html.parser")
    
    # Extract articles
    article_links = extract_articles_from_page(soup, limit)
    
    if not article_links:
        print("WARNING: No articles found on the page")
    else:
        print(f"Successfully found {len(article_links)} articles")
    
    # Fetch details for each article
    items = []
    for idx, (date_text, title, url) in enumerate(article_links, 1):
        print(f"[{idx}/{len(article_links)}] Fetching details: {url}")
        img_url, desc = fetch_article_details(url)
        items.append({
            "date": date_text,
            "title": title,
            "description": desc[:600] if desc else "No description available.",
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
        print("=" * 60)
        print("Toyota Canada News Scraper")
        print("=" * 60)
        
        news_data = fetch_toyota_news(limit=5)
        
        # Create directory if it doesn't exist
        os.makedirs("powerbi", exist_ok=True)
        
        # Write JSON file
        output_path = "powerbi/toyota_news.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(news_data, f, ensure_ascii=False, indent=2)
        
        print("=" * 60)
        print(f"✓ Successfully wrote {len(news_data['articles'])} articles to {output_path}")
        print("=" * 60)
        
        # Show summary
        for idx, article in enumerate(news_data['articles'], 1):
            print(f"{idx}. {article['date']} - {article['title'][:60]}...")
        
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