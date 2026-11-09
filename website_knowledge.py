"""Read public Mebel catalog; no customer history or contact data leaves for search."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import logging
import re
from time import monotonic
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import requests

ORIGIN = 'https://mebel.billbry.id'
log = logging.getLogger(__name__)
# Stable business/services information verified against the public homepage 2026-11-05.
PROFILE = {
    'source': ORIGIN + '/',
    'verified_on': '2026-11-05',
    'business': 'UD BILLBRY MEBEL',
    'address': 'Jl. Irian, Ngasinan, Jetis, Ponorogo',
    'services': ['Furniture custom untuk rumah, kantor, dan tempat usaha',
                 'Kitchen set, meja kasir, konter display, etalase, kabinet',
                 'Pintu, kusen dan jendela kayu',
                 'CNC router/ukir/relief, penggergajian dan bubut kayu',
                 'Kayu gelondongan, kayu gergajian, papan, balok dan aksesori furniture'],
    'custom': 'Desain, ukuran, material, finishing, ketersediaan dan harga final dikonfirmasi admin.',
    'images': 'Gambar kategori dapat berupa ilustrasi desain; bukan bukti produksi semua model.'
}
TERMS = (
    'kaki meja', 'meja kerja', 'meja belajar', 'meja laptop', 'meja makan', 'meja rias',
    'meja tv', 'meja konsol', 'meja kasir', 'coffee table', 'side table',
    'kursi tamu', 'kursi cafe', 'kursi makan', 'rak sepatu', 'rak buku', 'rak tanaman',
    'rak dinding', 'rak serbaguna', 'lemari pakaian', 'tempat tidur', 'kitchen set',
    'kayu gelondongan', 'kayu gergajian', 'penggergajian', 'cnc', 'bubut',
    'etalase', 'konter', 'kabinet', 'nakas', 'bufet', 'bangku', 'stool', 'lemari',
    'meja', 'kursi', 'rak', 'laci', 'pintu', 'kusen', 'jendela', 'papan', 'balok', 'kayu', 'jam hias')
TERM_RE = re.compile(r'\b(?:' + '|'.join(re.escape(x) for x in sorted(TERMS, key=len, reverse=True)) + r')\b', re.I)


def search_term(text):
    text = text.lower().replace('buffet', 'bufet')
    latest = text.rsplit('pesan pelanggan terbaru:', 1)[-1]
    matches = list(TERM_RE.finditer(latest)) or list(TERM_RE.finditer(text[-5000:]))
    return matches[-1].group(0) if matches else ''


def safe_url(value):
    url = urljoin(ORIGIN, value)
    p = urlparse(url)
    if p.scheme != 'https' or p.netloc != 'mebel.billbry.id' or p.username or p.password:
        raise ValueError('website_url_out_of_scope')
    return url


def fetch_page(url, params=None, *, deadline=None):
    # Follow only public website redirects on the exact allowed origin.
    for _ in range(4):
        url = safe_url(url)
        timeout = (15, 10)
        if deadline is not None:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise requests.Timeout()
            timeout = (min(2, remaining / 2), min(3, remaining / 2))
        with requests.get(url, params=params, timeout=timeout, allow_redirects=False,
                          stream=True) as r:
            if r.status_code in {301, 302, 303, 307, 308}:
                url = safe_url(urljoin(url, r.headers['Location']))
                params = None
                continue
            r.raise_for_status()
            if 'text/html' not in r.headers.get('Content-Type', ''):
                raise ValueError('website_not_html')
            chunks, size = [], 0
            for chunk in r.iter_content(16384):
                if deadline is not None and monotonic() >= deadline:
                    raise requests.Timeout()
                size += len(chunk)
                if size > 750000:
                    raise ValueError('website_too_large')
                chunks.append(chunk)
            return BeautifulSoup(b''.join(chunks), 'html.parser')
    raise ValueError('website_redirect_limit')


def listing(soup, term):
    items = []
    for card in soup.select('article.oe_product_cart'):
        title = card.select_one('.o_wsale_products_item_title a')
        if not title:
            continue
        name = title.get_text(' ', strip=True)
        if not all(word in name.lower() for word in term.split()):
            continue
        try:
            url = safe_url(title.get('href', ''))
        except ValueError:
            continue
        if not re.fullmatch(r'/(?:en/)?shop/[^/?#]+-\d+', urlparse(url).path):
            continue
        price = card.select_one('[aria-label="Sale price"]')
        price_text = price.get_text(' ', strip=True) if price else ''
        items.append({'name': name[:160], 'url': url,
                      'listed_price': price_text[:80] if re.search(r'Rp\s*[\d.,]+', price_text) else None})
    return items[:8]


def detail(item, *, deadline=None):
    result = dict(item)
    try:
        soup = fetch_page(item['url'], deadline=deadline)
        description = soup.select_one('#product_full_description, #product_details .o_wsale_product_details_content_section_title .oe_structure')
        if description:
            for junk in description.select('script,style,iframe,form,nav,header,footer'):
                junk.decompose()
            result['description'] = description.get_text(' ', strip=True)[:2400]
        notes = [p.get_text(' ', strip=True) for p in soup.select('#product_details p')
                 if re.search(r'harga.*pajak|pajak.*checkout|ongkir.*konfirmasi', p.get_text(' ', strip=True), re.I)]
        product_details = soup.select_one('#product_details')
        if product_details:
            notes += [t for t in product_details.stripped_strings if 'pajak' in t.lower()]
        notes = list(dict.fromkeys(notes))
        if notes:
            result['price_notes'] = [n[:500] for n in notes[:3]]
        sku = soup.select_one('[itemprop="sku"]')
        if sku:
            result['sku'] = (sku.get('content') or sku.get_text(' ', strip=True))[:100]
    except (requests.RequestException, ValueError, KeyError):
        result['description_status'] = 'unavailable'
    return result


def context_for(text, *, budget_seconds=None):
    deadline = None if budget_seconds is None else monotonic() + budget_seconds
    context = {'business_profile': PROFILE}
    term = search_term(text)
    if term:
        context['catalog_query'] = term  # Only known product terms, never customer text.
        try:
            items = listing(fetch_page(ORIGIN + '/en/shop', params={'search': term}, deadline=deadline), term)
            with ThreadPoolExecutor(max_workers=2) as pool:
                details = list(pool.map(lambda item: detail(item, deadline=deadline), items[:2]))
            context['products'] = details + items[2:]
            context['catalog_checked_at'] = datetime.now(timezone.utc).isoformat()
            context['catalog_status'] = 'found' if items else 'no_matching_product'
        except (requests.RequestException, ValueError, KeyError):
            context['catalog_status'] = 'unavailable'
            log.warning('mebel_catalog_unavailable')
    else:
        context['catalog_status'] = 'no_product_query'
    # Keep source context ahead of the recent conversation within Gemini's 20k input cap.
    while len(json.dumps(context, ensure_ascii=False)) > 9500 and context.get('products'):
        context['products'].pop()
    return json.dumps(context, ensure_ascii=False)
