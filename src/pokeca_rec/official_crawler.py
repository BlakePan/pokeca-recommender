import concurrent.futures
import logging
import os
import re
import sqlite3
import sys
import threading
import time
from sqlite3 import Connection, Cursor
from typing import Any, Dict, List, Union

from selenium import webdriver
from selenium.common.exceptions import (NoSuchElementException,
                                        WebDriverException)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from tqdm import tqdm

from pokeca_rec.deck_crawler import crawl_deck
from pokeca_rec.utils.chrome_option import chrome_opt
from pokeca_rec.utils.font import full2half
from pokeca_rec.utils.selenium_helper import find_elements, wait_invisibility

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


def wait_loading_circle(driver, timeout: int = 20):
    """Waits for an element with the class `sk-circle-container`
    (a loading circle) to become invisible on the page.

    Args:
        driver (WebDriver): A Selenium web driver instance.
        timeout (int, optional): The maximum time to wait for the element
        to become invisible. Defaults to 20.

    Raises:
        TimeoutError: If the element does not become invisible
        within the specified timeout.
    """
    wait_invisibility(
        driver,
        By.XPATH,
        "//div[@class='sk-circle-container']",
        wait_time=timeout,
    )


def get_event_meta(event_element: WebElement) -> Dict[str, Union[int, str]]:
    """Extract metadata for an event from the given event element.

    Parameters:
        event_element (WebElement):
        The WebElement representing an event on a webpage.

    Returns:
        Dict[str, Union[int, str]]:
        A dictionary containing the metadata for the event.
        The keys of the dictionary are 'num_players' and 'event_link',
        and the values are the corresponding integer value for
        the number of players and the string value for the event link.
    """

    num_players_str = find_elements(
        event_element, By.CLASS_NAME, "capacity", wait_time=5
    )[0].text
    num_players = re.findall(r"\d+", num_players_str)
    num_players = (
        int(num_players[0])
        if isinstance(num_players, List) and len(num_players) == 1
        else -1
    )

    event_link = event_element.get_attribute("href")

    address = find_elements(
        event_element, By.CLASS_NAME, "building", wait_time=5
    )[0].text
    address = full2half(address)
    for prefecture_name in ["県", "都", "府", "北海道"]:
        if prefecture_name in address:
            index = address.find(prefecture_name)
            index = index + len(prefecture_name)
            address = address[:index]
            break
    prefecture = address.split(" ")[-1]

    return {
        "num_players": num_players,
        "event_link": event_link,
        "prefecture": prefecture,
    }


def extract_deck_meta(
    deck_elem: WebElement, skip_codes: List[str]
) -> Dict[str, Any]:
    """Parses metadata for a deck from a WebElement
    representing a deck in a deck list table.

    Parameters:
    deck_elem (WebElement): WebElement representing
    a deck in a deck list table.

    skip_codes (List[str]): List of deck codes to skip.

    Returns:
    Dict[str, Any]: Dictionary containing metadata for the deck.
    """

    # Extract the URL for the deck element
    url = find_elements(
        find_elements(deck_elem, By.CLASS_NAME, "deck", wait_time=5)[0],
        By.TAG_NAME,
        "a",
        wait_time=5,
    )[0].get_property("href")

    # Extract the deck code from the URL
    deck_code = url.split("/")[-1]
    if deck_code in skip_codes:
        return None

    # Extract the rank of the deck element
    tag = find_elements(deck_elem, By.TAG_NAME, "td", wait_time=5)[0]
    rank = int(tag.get_attribute("class").split("-")[-1])

    return {
        "url": url,
        "deck_code": deck_code,
        "rank": rank,
    }


def crawl_deck_pages(
    deck_metas: List[Dict[str, Any]],
    cursor: Cursor = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Crawl the pages of the given deck metadata in parallel using threads.

    Parameters:
    - deck_metas (List[Dict[str, Any]]):
    a list of dictionaries containing metadata for each deck,
    including the url, deck code, rank, number of people, and date

    Returns:
    - Dict[str, List[Dict[str, Any]]]:
    a dictionary of lists of dictionaries containing
    the parsed information for each deck, grouped by category
    """

    # Create the shared dictionary
    results = []
    lock = threading.Lock()

    # Initialize an empty list to hold the results
    temp_results = []

    def crawl_deck_page(deck_meta):
        url = deck_meta["url"]
        deck_code = deck_meta["deck_code"]
        rank = deck_meta["rank"]
        num_players = deck_meta["num_players"]
        date = deck_meta["date"]
        prefecture = deck_meta["prefecture"]

        res = crawl_deck(deck_url=url, cursor=cursor)
        if res is None:
            return

        temp_results.append(
            {
                "deck_url": url,
                "deck_code": deck_code,
                "pokemons": res["pokemons"],
                "tools": res["tools"],
                "supporters": res["supporters"],
                "stadiums": res["stadiums"],
                "energies": res["energies"],
                "rank": rank,
                "num_players": num_players,
                "date": date,
                "prefecture": prefecture,
            }
        )

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=os.cpu_count()
    ) as executor:
        # Create a task for each deck
        threads = []
        for deck_meta in deck_metas:
            task = executor.submit(crawl_deck_page, deck_meta)
            threads.append(task)

        # Wait for all tasks to complete
        concurrent.futures.wait(threads)

        for out in concurrent.futures.as_completed(threads):
            logger.debug((out.result()))

    with lock:
        results = temp_results.copy()

    return results


def crawl_event_pages(
    event_link: str,
    num_players: int,
    prefecture: str,
    decks: Dict,
    skip_codes: List[str],
    num_pages: int = 1,
    cursor: Cursor = None,
) -> None:
    """
    Parse a given event page and collect metadata of available decks.

    Parameters:
    - event_link (str): the link of the event page
    - num_players (int): the number of players who participated in the event
    - prefecture (str): the prefecture of this event
    - decks (Dict): the dictionary to store the collected metadata
    - skip_codes (List[str]): the list of deck codes to skip
    - num_pages (int): the number of pages to parse (default: 1).
    If num_pages < 0, parse all pages.
    If num_pages = 0, no parsing.
    If num_pages = 1, parse pages for top-8.
    If num_pages = 2, parse pages for top-16.
    And so on.

    Returns:
    None
    """

    with webdriver.Chrome(options=chrome_opt) as driver:
        # Initialize the web driver
        driver.implicitly_wait(2)  # seconds

        # Navigate to the event page
        driver.get(event_link)
        date_str = find_elements(driver, By.CLASS_NAME, "date-day")[0].text

        t1 = time.time()
        deck_metas = []
        page_cnt = 0
        while page_cnt < num_pages:
            # Collect metadata of available decks
            deck_elems = find_elements(
                driver, By.CLASS_NAME, "c-rankTable-row", wait_time=5
            )
            for deck_idx, deck_elem in enumerate(deck_elems):
                try:
                    deck_meta = extract_deck_meta(deck_elem, skip_codes)
                    if deck_meta is None:
                        raise Exception(
                            "This deck is parsed before,"
                            "or there is an error while parsing deck meta "
                        )
                    deck_meta["num_players"] = num_players
                    deck_meta["date"] = date_str
                    deck_meta["prefecture"] = prefecture

                    # Calculate rank by rule-based, the risk will be the
                    # template on website changes to other format,
                    # so if the rank is not valid, just use the info
                    # parsed from the web element
                    rank = page_cnt * 8 + deck_idx + 1
                    rank_max = deck_meta["rank"] + deck_meta["rank"] - 1 - 1
                    if (
                        deck_meta["rank"] >= 3
                        and rank >= deck_meta["rank"]
                        and rank <= rank_max
                    ):
                        deck_meta["rank"] = rank

                    deck_metas.append(deck_meta)
                except Exception as e:
                    logger.debug(e)
                    logger.debug(event_link)
                    logger.debug(f"skip deck no. {deck_idx}")

            # nevigate to the next page
            try:
                page_cnt += 1
                if page_cnt < num_pages:
                    find_elements(driver, By.CLASS_NAME, "btn.next")[0].click()
                    wait_loading_circle(driver)
            except Exception as e:
                if isinstance(e, TimeoutError):
                    logger.info("Wait for loading circle Timeout")
                elif isinstance(e, NoSuchElementException):
                    if num_pages:
                        logger.info("Next deck page not found")
                    else:
                        logger.info("There is no next deck page")
                logger.debug(e)
                logger.debug(event_link)
                break
        t2 = time.time()
        logger.debug(f"Page Time diff part1: {t2-t1}")

        # wait for results
        logger.debug(deck_metas)
        t1 = time.time()
        results = crawl_deck_pages(deck_metas, cursor=cursor)
        t2 = time.time()
        logger.debug(f"Page Time diff part2: {t2-t1}")

        # update crawl results to decks
        if date_str not in decks:
            decks[date_str] = results
        else:
            decks[date_str] += results


def crawl_result_pages(
    league: str,
    skip_codes: List[int] = None,
    result_page_limit: int = 10,
    event_page_limit: int = 100,
    deck_page_limit: int = 1,
    start_page_num: int = 1,
    card_db: str = "db/ptcg_card.db",
) -> None:
    """Parses CL event links and metadata from the official website.

    Args:
        league (str):
        "City" or "Champion" league.

        skip_codes (List[int], optional):
        A list of deck codes to skip. Defaults to None.

        result_page_limit (int, optional):
        The maximum number of result pages to parse. Defaults to 10.

        event_page_limit (int, optional):
        The maximum number of event pages to parse. Defaults to 100.

        deck_page_limit (int, optional):
        The maximum number of deck pages to parse for each event.
        If num_pages < 0, parse all pages.
        If num_pages = 0, no parsing.
        If num_pages = 1, parse pages for top-8.
        If num_pages = 2, parse pages for top-16.
        And so on.

        start_page_num (int, optional):
        The number for first event page to crawl. Default to 1.

        Returns:
        decks (Dict): A dictionary to store the parsed CL event data.
    """
    if league not in ["City", "Champion"]:
        raise ValueError(
            f'Only support "City" or "Champion" league, input is {league}'
        )
    if league == "Champion":
        league = "チャンピオンズリーグ"
    elif league == "City":
        league = "シティリーグ"
    skip_codes = [] if skip_codes is None else skip_codes
    start_page_num = (
        start_page_num
        if isinstance(start_page_num, int) and start_page_num >= 1
        else 1
    )
    offset = (start_page_num - 1) * 20

    # connect to card db
    try:
        conn = sqlite3.connect(card_db)
        cursor = conn.cursor()
    except:
        conn = None
        cursor = None

    # parse CL/ChpL event links from official website
    decks = {}
    url = f"https://players.pokemon-card.com/event/result/list?offset={offset}"
    with webdriver.Chrome(options=chrome_opt) as driver:
        try:
            # Initialize the web driver
            driver.implicitly_wait(2)  # seconds
            driver.get(url)
        except Exception as e:
            if isinstance(e, WebDriverException):
                logger.info("WebDriverException when parsing result link")
            else:
                logger.info("Error when parsing result link")
            logger.debug(e)
            return

        result_page_cnt = 0
        event_page_cnt = 0
        while (
            result_page_cnt < result_page_limit
            and event_page_cnt < event_page_limit
        ):
            logger.info(f"Processing result page: {result_page_cnt}")
            try:
                events = find_elements(driver, By.CLASS_NAME, "eventListItem")
                for event in tqdm(
                    events, desc=f"Processing result page: {result_page_cnt}"
                ):
                    title = find_elements(
                        event, By.CLASS_NAME, "title", wait_time=5
                    )[0]
                    if league not in title.text:
                        continue

                    event_meta = get_event_meta(event)

                    t1 = time.time()
                    crawl_event_pages(
                        event_meta["event_link"],
                        event_meta["num_players"],
                        event_meta["prefecture"],
                        decks=decks,
                        skip_codes=skip_codes,
                        num_pages=deck_page_limit,
                        cursor=cursor,
                    )
                    t2 = time.time()
                    logger.debug(f"Event Time diff part1: {t2 - t1}")

                    event_page_cnt += 1
                    if event_page_cnt >= event_page_limit:
                        break

            except Exception as e:
                # Error handling:
                # - log exception
                # - skip this result page
                if isinstance(e, WebDriverException):
                    logger.info("WebDriverException when parsing event link")
                    logger.info(
                        "This situation might cause by"
                        "unstable network connection,"
                        "please try to run the program again"
                    )
                else:
                    logger.info("Error when parsing event link")
                logger.debug(e)
                logger.debug(f"Processing result page: {result_page_cnt}")

            # nevigate to the next result page
            result_page_cnt += 1
            try:
                find_elements(driver, By.CLASS_NAME, "btn.next")[0].click()
                wait_loading_circle(driver)
            except Exception as e:
                if isinstance(e, TimeoutError):
                    logger.info("Wait for loading circle Timeout")
                elif isinstance(e, NoSuchElementException):
                    logger.info("Next event page not found")
                logger.debug(e)
                break

    if isinstance(conn, Connection):
        conn.close()

    return decks


if __name__ == "__main__":
    from pprint import pprint

    # deck_metas = [
    #     {
    #         "url": "https://www.pokemon-card.com/deck/confirm.html/deckID/NgnHHn-0Aixqe-iLniHL",
    #         "deck_code": "NgnHHn-0Aixqe-iLniHL",
    #         "rank": 1,
    #         "num_players": 64,
    #         "date": "2024年03月20日(水)",
    #         "prefecture": "神奈川県",
    #     },
    #     {
    #         "url": "https://www.pokemon-card.com/deck/confirm.html/deckID/NNngQn-3H6pJe-QL6iLH",
    #         "deck_code": "NNngQn-3H6pJe-QL6iLH",
    #         "rank": 2,
    #         "num_players": 64,
    #         "date": "2024年03月20日(水)",
    #         "prefecture": "神奈川県",
    #     },
    # ]
    # print("crawl_deck_pages()")
    # t1 = time.time()
    # res = crawl_deck_pages(deck_metas)
    # t2 = time.time()
    # pprint(res)
    # print(f"Ouput size: {len(res)}")
    # print(f"Crawling time: {t2 - t1}")
    # print()
    # print("crawl_event_pages")
    # decks = {}
    # t1 = time.time()
    # crawl_event_pages(
    #     event_link="https://players.pokemon-card.com/event/detail/308221/result",
    #     num_players=64,
    #     prefecture="東京都",
    #     decks=decks,
    #     skip_codes=[],
    # )
    # t2 = time.time()
    # pprint(decks)
    # print(f"Ouput size: {len(decks)}")
    # print(f"Crawling time: {t2 - t1}")
    # print()
    # print("crawl_result_pages() for Champion")
    # t1 = time.time()
    # decks = crawl_result_pages(
    #     league="Champion",
    #     result_page_limit=1,
    #     deck_page_limit=1,
    #     start_page_num=17,
    # )
    # t2 = time.time()
    # pprint(decks)
    # print(f"Ouput size: {len(decks)}")
    # print(f"Crawling time: {t2 - t1}")
    # print()

    print("crawl_result_pages() for City")
    t1 = time.time()
    decks = crawl_result_pages(
        league="City", result_page_limit=1, deck_page_limit=1, start_page_num=1
    )
    t2 = time.time()
    pprint(decks)
    print(f"Ouput size: {len(decks)}")
    print(f"Crawling time: {t2 - t1}")
    print()
