import ipaddress
import json
import re
import socket
from html import unescape
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

C_USER_AGENT = "CV-Builder/0.1 job application organizer"
INITIAL_DATA_PATTERN = re.compile(r"window\._initialData\s*=\s*(\{.*?\})\s*;", re.DOTALL)


def _public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Enter a valid http or https URL.")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not supported.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
    except socket.gaierror as exc:
        raise ValueError("The website address could not be resolved.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("Private and local network addresses are not allowed.")
    return url


def download_page(url: str) -> str:
    checked_url = _public_url(url)
    with httpx.Client(
        timeout=15,
        follow_redirects=True,
        headers={"User-Agent": C_USER_AGENT},
    ) as client:
        response = client.get(checked_url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type.lower():
            raise ValueError("The URL did not return an HTML page.")
        if len(response.content) > 5_000_000:
            raise ValueError("The page is too large to import.")
        return response.text


def extract_initial_data(html: str) -> dict | None:
    match = INITIAL_DATA_PATTERN.search(html)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _meta(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        if tag and tag.get("content"):
            return unescape(tag["content"]).strip()
    return ""


def parse_job_page(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()

    title = _meta(soup, "og:title", "twitter:title")
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)

    company = _meta(soup, "og:site_name")
    description = _meta(soup, "description", "og:description")

    job_node = (
        soup.select_one("#jobDescriptionText")
        or soup.select_one("[data-testid='jobsearch-JobComponent-description']")
        or soup.select_one("[class*='jobDescription']")
        or soup.select_one("main")
    )
    if job_node:
        job_text = job_node.get_text("\n", strip=True)
        if len(job_text) > len(description):
            description = job_text

    initial_data = extract_initial_data(html)
    return {
        "job_title": title[:250],
        "company": company[:250],
        "job_description": description[:50_000],
        "imported_data": json.dumps(initial_data, ensure_ascii=False)
        if initial_data
        else "",
    }
