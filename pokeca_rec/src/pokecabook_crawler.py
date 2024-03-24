import logging
import os
import sys
import time
import traceback
from collections import defaultdict
from typing import Dict, List

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tqdm import tqdm

sys.path.append(".")
from pokeca_rec.src.deck_crawler import crawl_deck
from pokeca_rec.utils.chrome_option import chrome_opt

# Create logging folder
LOG_FOLDER = "logs"
if not os.path.exists(LOG_FOLDER):
    os.makedirs(LOG_FOLDER)

# Set up logging to a file
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename=f"{LOG_FOLDER}/{os.path.basename(__file__)}.log",
    filemode="w",
)
logger = logging.getLogger(__name__)


# craw gym
# https://pokecabook.com/archives/category/tournament/jim-battle/page/1


def crawl_from_gym_page(
    url: str, progress_bar: bool = False
) -> Dict[str, List[Dict]]:
    """
    Crawls a gym page specified by the URL and extracts information about
    gym decks, including their categories and URLs.

    Parameters:
        url (str): The URL of the gym page to be crawled.
        progress_bar (bool, optional): Set True to turn on progress bar.
                                       Defaults to False.

    Returns:
        Dict[str, List[str]]: A dictionary where each key is a deck category
        (as a string) and each value is a list of deck dict

    Raises:
        AssertionError: If the number of deck categories does not match the
                        number of deck URLs extracted from the page.
        Exception: If any error occurs during the crawling process, the error
                   is logged, and None is returned.
    """

    gym_decks = defaultdict(list)
    with webdriver.Chrome(options=chrome_opt) as driver:
        # Initialize the web driver
        driver.implicitly_wait(2)  # seconds
        try:
            with webdriver.Chrome(options=chrome_opt) as driver:
                driver.get(url)
                deck_category_items = WebDriverWait(driver, 10).until(
                    EC.visibility_of_all_elements_located(
                        (
                            By.CSS_SELECTOR,
                            ".wp-block-heading.has-medium-font-size:"
                            "not(.has-text-align-center)",
                        )
                    )
                )
                deck_categories = []
                for dc_item in deck_category_items:
                    deck_categories.append(
                        (
                            WebDriverWait(dc_item, 10).until(
                                EC.presence_of_element_located(
                                    (By.TAG_NAME, "span")
                                )
                            )
                        ).text
                    )
                deck_urls = WebDriverWait(driver, 10).until(
                    EC.visibility_of_all_elements_located(
                        (By.CSS_SELECTOR, ".wp-element-caption")
                    )
                )
                deck_urls = [
                    du_item.find_element(By.TAG_NAME, "a").get_attribute(
                        "href"
                    )
                    for du_item in deck_urls
                ]

                assert len(deck_categories) == len(
                    deck_urls
                ), f"""assume len(deck_categories) == len(deck_urls),
                    but got len(deck_categories) = {len(deck_categories)},
                    len(deck_urls) = {len(deck_urls)}"""

                pbar = tqdm(
                    zip(deck_categories, deck_urls), disable=not progress_bar
                )
                for category, deck_url in pbar:
                    pbar.set_description(f"Crawling {deck_url.split('/')[-2]}")
                    gym_decks[category].append(crawl_deck(deck_url=deck_url))

        except Exception as e:
            logger.info(f"An error occurred crawl_from_gym_page: {e}")
            logger.debug(e)
            logger.debug(traceback.format_exc())
            return None

    return gym_decks


def crawl_gym_decks(
    page_start: int,
    num_pages: int = 1,
    progress_bar_lv1: bool = False,
    progress_bar_lv2: bool = False,
) -> Dict[str, Dict[str, List[Dict]]]:
    """
    Crawls multiple pages of gym decks starting from a specified page and
    collects gym deck information including URLs and dates. It aggregates
    the data in a nested dictionary structure keyed by the gym date.

    Parameters:
        page_start (int): The starting page number for crawling. Must be an
                          integer greater than or equal to 1.
        num_pages (int, optional): The number of pages to crawl from the start
                                   page. Defaults to 1. Must be an integer
                                   greater than or equal to 1.
        progress_bar_lv1 (bool, optional): Set True to turn on progress bar
                                           for this level. Defaults to False.
        progress_bar_lv2 (bool, optional): Set True to turn on progress bar
                                           for deeper level. Defaults to False.

    Returns:
        Dict[str, Dict[str, List[Dict]]]: A dictionary with gym dates as keys.
        Each key maps to another dictionary, which is the result of
        `crawl_from_gym_page`, containing detailed information about gym decks
        for that date.

    Raises:
        AssertionError: If `page_start` or `num_pages` is not an integer or is
                        less than 1.
    """

    assert (
        isinstance(page_start, int) and page_start >= 1
    ), f"""assume page_start is int but got type: {type(page_start)}.
    assuem page_start >= 1 but got: {page_start}"""

    assert (
        isinstance(num_pages, int) and num_pages >= 1
    ), f"""assume num_pages is int but got type: {type(num_pages)}.
    assuem num_pages >= 1 but got: {num_pages}"""

    gym_decks = {}
    url = (
        "https://pokecabook.com/archives/category/tournament/jim-battle/page/"
    )
    for page_num in range(page_start, page_start + num_pages):
        url_ = url + str(page_num)
        with webdriver.Chrome(options=chrome_opt) as driver:
            # Initialize the web driver
            driver.implicitly_wait(2)  # seconds
            try:
                driver.get(url_)
                list_items = WebDriverWait(driver, 10).until(
                    EC.visibility_of_all_elements_located(
                        (
                            By.CLASS_NAME,
                            "entry-card-wrap.a-wrap.border-element.cf",
                        )
                    )
                )
                for list_item in tqdm(
                    list_items,
                    desc=f"page: {page_num}",
                    disable=not progress_bar_lv1,
                ):
                    gym_page_url = list_item.get_attribute("href")
                    gym_date = (
                        WebDriverWait(list_item, 10)
                        .until(
                            EC.presence_of_element_located(
                                (By.CLASS_NAME, "entry-date")
                            )
                        )
                        .text
                    )
                    gym_decks[gym_date] = crawl_from_gym_page(
                        gym_page_url, progress_bar=progress_bar_lv2
                    )
            except Exception as e:
                logger.info(f"An error occurred crawl_gym_decks: {e}")
                logger.debug(e)
                logger.debug(traceback.format_exc())
                return None

    return gym_decks


if __name__ == "__main__":
    from pprint import pprint

    print("crawl_from_gym_page")
    t1 = time.time()
    gym_decks = crawl_from_gym_page(
        "https://pokecabook.com/archives/110398", progress_bar=True
    )
    t2 = time.time()
    pprint(gym_decks)
    print(f"time diff: {t2-t1}\n")

    print("crawl_gym_decks")
    t1 = time.time()
    gym_decks = crawl_gym_decks(
        1, progress_bar_lv1=True, progress_bar_lv2=True
    )
    t2 = time.time()
    pprint(gym_decks)
    print(f"time diff: {t2-t1}")
