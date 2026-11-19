"""Helpers for the DGCA portal (pages load via POST to /scan?, files live on S3)."""

import html
import re
import time

import requests

PORTAL = "https://www.dgca.gov.in/digigov-portal"
S3_BASE = "https://public-prd-dgca.s3.ap-south-1.amazonaws.com/"
HEADERS = {"User-Agent": "Mozilla/5.0 (portfolio data project; DGCA public statistics)"}
PAGE_RETRIES = 4


def new_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    session.get(f"{PORTAL}/?baseLocale=en_US", timeout=60)
    return session


def fetch_page(session, rulebook_id, content_id):
    form = {
        "baseLocale": "en_US",
        "screenId": "10000001",
        "actionVal": "viewStaticData",
        "requestType": "ApplicationRH",
        "attachId": "",
        "langType": "1",
        "ruleBookId": str(rulebook_id),
        "contentId": str(content_id),
        "serviceName": "getParentData",
        "attr": "",
    }
    for attempt in range(1, PAGE_RETRIES + 1):
        try:
            resp = session.post(
                f"{PORTAL}/scan?",
                data=form,
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            break
        except (requests.RequestException, ValueError) as exc:
            if attempt == PAGE_RETRIES:
                raise
            wait = 10 * attempt
            print(f"    portal error ({exc.__class__.__name__}), retrying in {wait}s")
            time.sleep(wait)
    items = data.get("ruleBookContentDtlsList") or [data]
    content = items[0].get("contentText")
    if not content:
        raise RuntimeError(f"Portal page {rulebook_id}/{content_id} came back empty; the site may have changed.")
    return content


def clean_text(fragment):
    text = re.sub(r"<[^>]+>", " ", fragment)
    text = html.unescape(text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def find_links(fragment):
    return [
        (html.unescape(url), clean_text(text))
        for url, text in re.findall(r'<a[^>]*data-url="([^"]+)"[^>]*>(.*?)</a>', fragment, re.S | re.I)
    ]


def table_rows(page_html):
    return [
        re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page_html, re.S | re.I)
    ]


def page_ids(data_url):
    m = re.fullmatch(r"[A-Za-z]+/(\d+)/(\d+)/html", data_url)
    return m.groups() if m else None


def file_url(data_url):
    return S3_BASE + data_url.replace("jsp/dgca/", "", 1)
