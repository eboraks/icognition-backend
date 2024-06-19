from datetime import datetime
import requests
import logging
import re
from bs4 import BeautifulSoup
from app.models import Page, PagePayload
import urllib.parse as urlparse
from dateutil.parser import parse

logging.basicConfig(
    format="%(asctime)s,%(msecs)03d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s",
    datefmt="%Y-%m-%d:%H:%M:%S",
    level=logging.DEBUG,
)

logger = logging.getLogger(__name__)

MININUM_PARAGRAPH_LENGTH = 10


def get_keywords(tags: dict) -> list[str]:
    """Extract keywords from meta tags

    Args:
        tags (dict): Meta tags

    Returns:
        list[str]: List of keywords
    """
    keywords = []
    if "news_keywords" in tags:
        keywords = tags["news_keywords"].split(",")
        return keywords
    
    if "keywords" in tags:
        keywords = tags["keywords"].split(",")
        return keywords
    
    for key in tags:
        if "article:tag" in key:
            keywords.append(tags[key])


def get_authors(tags: dict) -> set[str]:
    """Extract author from meta tags

    Args:
        tags (dict): Meta tags

    Returns:
        str: list author name
    """

    authers = set()
    for key in tags:
        if "author" in key:
            authers.add(tags[key])
    
        if "parsely-author" in tags:
            authers.add(tags["parsely-author"])
    
        if "article:author" in tags:
            authers.add(tags["article:author"])
    
    return authers

def get_locale(tags: dict) -> str:
    """Extract locale from meta tags

    Args:
        tags (dict): Meta tags

    Returns:
        str: locale
    """
    if "og:locale" in tags:
        return tags["og:locale"]
    else:
        return None

def get_publish_date(tags: dict) -> datetime:
    """Extract publish date from meta tags

    Args:
        tags (dict): Meta tags

    Returns:
        str: publish date
    """
    if "article:published_time" in tags:
        strdate = tags["article:published_time"]
        return parse(strdate)
    else:
        return None

def get_image_url(tags: dict) -> str:
    """Extract image from meta tags

    Args:
        tags (dict): Meta tags

    Returns:
        str: image url
    """
    if "og:image" in tags:
        return tags["og:image"]
    else:
        return None
    
def get_title(tags: dict) -> str:
    """Extract title from meta tags

    Args:
        tags (dict): Meta tags

    Returns:
        str: title
    """
    if "og:title" in tags:
        return tags["og:title"]
    else:
        return None
    
def get_site_name(tags: dict) -> str:
    """Extract site name from meta tags

    Args:
        tags (dict): Meta tags

    Returns:
        str: site name
    """
    if "og:site_name" in tags:
        return tags["og:site_name"]
    else:
        return None

def get_url(tags: dict) -> str:
    """Extract url from meta tags

    Args:
        tags (dict): Meta tags

    Returns:
        str: url
    """
    if "og:url" in tags:
        return tags["og:url"]
    else:
        return None

def get_description(tags: dict) -> str:
    """Extract description from meta tags

    Args:
        tags (dict): Meta tags

    Returns:
        str: description
    """
    if "og:description" in tags:
        return tags["og:description"]
    else:
        return None


def get_meta_tags(soup: BeautifulSoup) -> dict:

    """
    Examples of tags of interest:
    <meta data-rh="true" property="article:content_tier" content="metered">
    <meta data-rh="true" property="article:tag" content="Gaza Strip">
    <meta data-rh="true" name="news_keywords" content="Gaza Strip,Israel,West Bank,Benjamin Netanyahu,Palestinians,Judaism,Israel Gaza War,Israeli settlement,Civilian casualties">
    <meta data-rh="true" http-equiv="Content-Language" content="en">
    <meta property="og:locale" content="en_US">
    <meta data-rh="true" property="article:published_time" content="2024-05-16T18:40:06.000Z">
    <meta data-rh="true" property="og:url" content="https://www.nytimes.com/2024/05/16/opinion/israeli-palestine-psyche.html">
    <meta data-rh="true" property="og:title" content="Opinion | The View Within Israel Turns Bleak">
    <meta data-rh="true" property="og:image" content="https://static01.nyt.com/images/2024/05/18/multimedia/17stack-3-hkpc/17stack-3-hkpc-facebookJumbo.jpg">
    <meta data-rh="true" property="og:description" content="Attitudes toward the “Palestinian problem” range from detached fatigue to the belief that driving Palestinians into submission is God’s work.">
    <meta data-rh="true" property="og:type" content="article">
    <meta property="og:site_name" content="The Atlantic">
    <meta name="author" content="Ed Yong">
    <meta name="parsely-author" content="Jan-Patrick Barnert">
    <meta data-rh="true" property="article:author" content="https://www.nytimes.com/by/megan-k-stack">
    <meta data-rh="true" property="og:site_name" content="Medium">
    """
    
    meta_tags = {}
    for tag in soup.find_all("meta"):
        if tag.get("property") is not None:
            meta_tags[tag.get("property")] = tag.get("content")
        elif tag.get("name") is not None:
            meta_tags[tag.get("name")] = tag.get("content")
        elif tag.get("http-equiv") is not None:
            meta_tags[tag.get("http-equiv")] = tag.get("content")

    return meta_tags


def get_webpage(payload: PagePayload) -> BeautifulSoup:
    """_summary_

    Args:
        url (str): URL of the page

    Returns:
        BeautifulSoup: BeatifulSoup object
    """
    try:

        if payload.html:
            logging.info("Html_parser -> get_webpage -> Using payload html")
            return BeautifulSoup(payload.html, "html.parser")

        logging.info("Html_parser -> get_webpage -> requests.get -> payload.url")
        response = requests.get(payload.url)
        content = response.text
        return BeautifulSoup(content, "html.parser")
    except requests.exceptions.InvalidSchema as e:
        logging.error(
            f"InvalidSchema wrror getting webpage: {payload.url} with error: {e}"
        )
        return None
    except Exception as e:
        logging.error(f"Error getting webpage: {payload.url} with error: {e}")
        return None


def find_main_article_element(soup: BeautifulSoup) -> list[str]:

    articles = []
    selectors = ["div#article", "div.article-body", "div.article", "div.article-container", "article", "main"]

    for selector in selectors:
        for element in soup.select(selector):
            articles.append(element)

    if len(articles) == 0:
        return None

    content_estimator = []
    for article in articles:
        num_contect_ele = len(article.find_all("h1")) + len(article.find_all("h2")) + len(article.find_all("p"))
        content_estimator.append(num_contect_ele)

    if len(content_estimator) == 0:
        return None

    logging.info(content_estimator)
    if max(content_estimator) < 3:
        logging.warning("Not enought content on the page")
        raise ValueError("Not enough contect on the page")

    # Select the article element with the most content
    main_article = articles[content_estimator.index(max(content_estimator))]

    return main_article


def get_paragraphs(soup: BeautifulSoup) -> list[str]:
    header_pattern = re.compile(r"h\d")
    text_elements = []
    for element in soup.find_all(["p", "h1", "h2", "h3"]):
        ## Collect only paragraph and headers with enough content
        if element.name == "p" and len(element.text.split(" ")) > 8:
            text_elements.append(element.text)
        elif header_pattern.match(element.name) and len(element.text.split(" ")) > 3:
            text_elements.append(element.text)
        else:
            None
    return text_elements

def get_elements(soup: BeautifulSoup) -> list[str]:
    header_pattern = re.compile(r"h\d")
    elements = []
    for element in soup.find_all(["p", "h1", "h2", "h3"]):
        ## Collect only paragraph and headers with enough content
        if element.name == "p" and len(element.text.split(" ")) > 8:
            elements.append(element)
        elif header_pattern.match(element.name) and len(element.text.split(" ")) > 3:
            elements.append(element)
        else:
            None
    return elements


def clean_url(url: str) -> str:
    """Clean URL from trailing characters

    Args:
        url (str): _description_

    Returns:
        str: _description_
    """
    url = urlparse.unquote(url)
    # Define the regex
    page_regex = r"(http.*:\/\/[a-zA-Z0-9:\/\.\-\@\%\_]*)"

    # Match the regex against the URL
    matches = re.findall(page_regex, url)

    # Get the first match
    if matches:
        clean_url = matches[0]
    else:
        # If no match, use the URL as the page URL
        clean_url = url

    return clean_url


def create_page(payload: PagePayload) -> Page:

    html = get_webpage(payload)
    if html is None:
        logging.error("No webpage found")
        return None

    

    article_element = find_main_article_element(html)

    if article_element is None:
        return None

    paragraphs = get_paragraphs(article_element)
    elements = get_elements(article_element)

    if paragraphs is None:
        logging.error("No paragraphs found in webpage")
        return None

    metatags = get_meta_tags(html)

    page = Page()
    page.paragraphs = paragraphs
    page.authors = get_authors(metatags)
    page.full_text = "\n".join(paragraphs)
    page.title = get_title(metatags)
    page.keywords = get_keywords(metatags)
    page.locale = get_locale(metatags)
    page.publish_date = get_publish_date(metatags)
    page.image_url = get_image_url(metatags)
    page.site_name = get_site_name(metatags)
    if page.site_name is None:
        page.site_name = urlparse.urlparse(payload.url).netloc
    page.clean_url = get_url(metatags)
    if page.clean_url is None:
        page.clean_url = clean_url(payload.url)
    page.metadata_description = get_description(metatags)


    return page


def unsupported_page_url(url: str) -> bool:
    """Making sure the URL is for supported page. No home page, no search pages

    Args:
        url (str): URL of the page

    Returns:
        bool: True if the URL is supported, False otherwise
    """
    # Define the regex
    regexs = []
    regexs = [r"^https?://[^/]+/$", r"^https?://[^/]+/search\?q=.+$"]

    for regex in regexs:
        if re.match(regex, url):
            return True
    
    return False