import json
import logging
import os
import sqlite3
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path
from sqlite3 import Cursor
from typing import Dict, List, Optional, Tuple

from selenium import webdriver
from selenium.common.exceptions import (NoSuchElementException,
                                        WebDriverException)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tqdm import tqdm

sys.path.append(".")
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


def map_card_code(
    card_name: str, card_code: str, cursor: Optional[Cursor] = None
) -> str:
    """This function maps multiple card codes to one which belongs to the same
    card. This happens when a card has multiple versions or re-sale.

    Args:
        card_name (str): A card name.
        card_code (str): Current card code.
        cursor (Optional[Cursor]): A cursor to all product db.

    Returns:
        str: mapped card code
    """
    if cursor is None:
        return card_code

    query = """
    SELECT card_code_jp FROM ptcg_card
    WHERE card_name_jp = ?
    AND json_extract(card_code_jp, '$') LIKE ?
    """
    try:
        cursor.execute(query, [card_name, f"%{card_code}%"])
        results = cursor.fetchall()
        if len(results) != 1:
            raise ValueError(
                f"""The return result should be ONLY 1 but got {len(results)}
                            Please check db of {card_name} {card_code}"""
            )
        card_code_list = json.loads(
            results[0][0]
        )  # [('["SV5K-004/071", "SV5K-072/071"]',)]
        logging.debug(f"{card_name}: {card_code_list}")
        if len(card_code_list) < 0:
            raise ValueError(
                f"""The size of card code list should >= 1.
                             but got {len(card_code_list)} instead!"""
            )
        card_code = card_code_list[0]  # always use the first one

    except Exception as e:
        logger.info(f"An error occurred while quering card_code: {e}")
        logger.debug(e)
        logger.debug(traceback.format_exc())

    return card_code


def extract_card(cards: List[str]) -> Dict[str, int]:
    """Extracts information about cards from a list of strings
    and returns the information as a dictionary.

    Args:
        cards (List[str]): A list of strings containing card information.

    Returns:
        Dict[str, int]: A dictionary with keys representing card names
        and values representing card counts.
    """
    extracted_card_info = {}

    for card_string in cards[1:]:
        card_string = card_string.split(" ")
        card_name = " ".join(card_string[0:-1])
        num_cards = int(card_string[-1][:-1])
        character_index = -1
        for character in ["（", "("]:
            if character in card_name:
                character_index = card_name.find(character)

        # if there is a left parenthesis in the card name,
        # then the card name will be modified for removing chars
        # including and after the left parenthesis
        # otherwise, just keep the same card name
        card_name = card_name[:character_index] if character_index != -1 else card_name
        extracted_card_info[card_name] = num_cards

    return extracted_card_info


def crawl_deck(
    deck_id: str = None,
    deck_url: str = None,
    cursor: Cursor = None,
) -> Tuple:
    """Parses a deck and returns the card information
    as a tuple of dictionaries.

    Args:
        deck_id (str, optional): The id of the deck to parse.
        deck_url (str, optional): The URL of the deck to parse.

    Returns:
        Tuple[Dict[str, int], ...]:
            A tuple of dictionaries with keys representing card names and
            values representing card counts.
            The dictionaries represent the Pokemon cards, tool cards,
            supporter cards, stadium cards, and energy cards, respectively.
    """
    # Return early if neither a deck code nor a deck link is provided
    if not deck_id and not deck_url:
        return

    # Initialize dictionaries to store the card information
    pokemon_dict = {}  # {card_name: no.cards}
    tool_dict = {}
    supporter_dict = {}
    stadium_dict = {}
    energy_dict = {}

    # Use the deck link if provided,
    # otherwise generate the URL using the deck code
    url = (
        deck_url
        if deck_url
        else f"https://www.pokemon-card.com/deck/confirm.html/deckID/{deck_id}/"
    )

    with webdriver.Chrome(options=chrome_opt) as driver:
        # Initialize the web driver
        driver.implicitly_wait(2)  # seconds

        try:
            # Navigate to the deck page and click the "list view" button
            driver.get(url)

            # Click リスト表示
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "deckView01"))
            ).click()

            # Find the element containing the card information
            cardListView_item = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "cardListView"))
            )
            elems = WebDriverWait(cardListView_item, 10).until(
                EC.visibility_of_all_elements_located((By.CLASS_NAME, "Grid_item"))
            )

            for grid_item_elem in elems:
                if "ポケモン (" in grid_item_elem.text:
                    """
                    example:

                    ポケモン (11)
                    ジュラルドンVMAX
                    S8b
                    253/184
                    3枚
                    """
                    cards = grid_item_elem.text.split("\n")
                    for i in range(1, len(cards), 4):
                        card_name = cards[i]
                        card_code = cards[i + 1] + "-" + cards[i + 2]
                        card_code = map_card_code(card_name, card_code, cursor)
                        card_name = card_name + "\n" + card_code
                        num_cards = int(cards[i + 3][:-1])
                        if card_name not in pokemon_dict:
                            pokemon_dict[card_name] = 0
                        pokemon_dict[card_name] += num_cards
                else:
                    """
                    example:

                    グッズ (19)
                    クイックボール 3枚
                    """
                    grid_text = grid_item_elem.text
                    cards = grid_text.split("\n")
                    card_info = extract_card(cards)

                    if "グッズ (" in grid_text:
                        tool_dict = card_info
                    elif "サポート (" in grid_text:
                        supporter_dict = card_info
                    elif "スタジアム (" in grid_text:
                        stadium_dict = card_info
                    elif "エネルギー (" in grid_text:
                        energy_dict = card_info
        except Exception as e:
            logger.info(f"An error occurred while parsing the deck: {e}")
            logger.debug(e)
            logger.debug(traceback.format_exc())
            return None

    return {
        "pokemons": pokemon_dict,
        "tools": tool_dict,
        "supporters": supporter_dict,
        "stadiums": stadium_dict,
        "energies": energy_dict,
    }


if __name__ == "__main__":
    from pprint import pprint

    conn = sqlite3.connect("db/ptcg_card.db")
    cursor = conn.cursor()

    print("map_card_code():")
    t1 = time.time()
    card_name = "ハヤシガメ"
    card_code = "SV5K-072/071"  # ["SV5K-004/071", "SV5K-072/071"]
    mapped_card_code = map_card_code(card_name, card_code, cursor)
    print(f"{card_name}: {card_code} -> {mapped_card_code} ")
    t2 = time.time()
    print(f"time diff: {t2-t1}")
    print("\n")

    print("crawl_deck():")
    t1 = time.time()
    ret = crawl_deck(
        deck_id="2SXUSR-h31cri-RpyXMM", # check card code of リザードンex
        cursor=cursor,
    )
    t2 = time.time()
    print("pokemon_dict")
    pprint(ret["pokemons"])
    print("tool_dict")
    pprint(ret["tools"])
    print("supporter_dict")
    pprint(ret["supporters"])
    print("stadium_dict")
    pprint(ret["stadiums"])
    print("energy_dict")
    pprint(ret["energies"])
    print(f"time diff: {t2-t1}")
    print("\n")

    conn.close()
