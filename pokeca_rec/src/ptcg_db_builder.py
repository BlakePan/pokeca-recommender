import os
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
import subprocess

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tqdm import tqdm

sys.path.append(".")
from pokeca_rec.src.ptcg_product_crawler import (
    NOT_UNIQUE_COLS,
    PTCGProductCrawler,
)
from pokeca_rec.utils.chrome_option import chrome_opt
from pokeca_rec.utils.selenium_helper import find_element, find_elements

DROP_TABLE = False
DB_NAME = "ptcg_card"
TABLE_NAME = DB_NAME
DB_PATH = "../db"

"""Official Site URL"""
# URL = "https://www.pokemon-card.com/card-search/index.php?\
#     keyword=&se_ta=&regulation_sidebar_form=all&pg=&illust=&sm_and_keyword=true"  # expanded
URL = "https://www.pokemon-card.com/card-search/index.php?\
    keyword=&se_ta=&regulation_sidebar_form=XY&pg=&illust=&sm_and_keyword=true"  # standard


def get_total_num_card(driver: webdriver.Chrome) -> int:
    """
    Retrieves the total number of cards from a web page using the provided Selenium WebDriver.

    Args:
        driver (webdriver.Chrome): The Selenium WebDriver instance.

    Returns:
        int: The total number of cards as an integer.
    """

    def wait_for_non_zero_element(driver):
        element = driver.find_element(By.ID, "AllCountNum")
        return element if element.text != "0" else False

    counter = 0
    total_card_num = (
        WebDriverWait(driver, 10).until(wait_for_non_zero_element).text
    )

    # Wait for the total card number to stop updating
    while True:
        total_card_num_update = (
            WebDriverWait(driver, 10).until(wait_for_non_zero_element).text
        )
        if total_card_num_update == total_card_num:
            counter += 1
            if counter > 10:
                total_card_num = total_card_num_update
                break
        else:
            total_card_num = total_card_num_update
            counter = 0

    return int(total_card_num)


def get_total_num_page(driver: webdriver.Chrome) -> int:
    """
    Get the total number of pages from the web page.

    Args:
        driver (webdriver.Chrome): The Chrome webdriver instance.

    Returns:
        int: The total number of pages.
    """
    all_num_element = driver.find_element(By.CLASS_NAME, "AllNum")
    number_of_pages = int(all_num_element.text)
    return number_of_pages


class PTCGDatabaseBuilder:
    def __init__(
        self,
        url: str = URL,
        db_name: str = DB_NAME,
        table_name: str = TABLE_NAME,
        db_path: str = DB_PATH,
        is_drop_table: bool = DROP_TABLE,
        num_card: int = None,
        num_page: int = None,
    ):
        self.url = url
        self.db_name = (
            db_name if db_name and isinstance(db_name, str) else DB_NAME
        )
        self.table_name = (
            table_name
            if table_name and isinstance(table_name, str)
            else TABLE_NAME
        )
        self.is_drop_table = is_drop_table
        db_path = db_path if db_path and isinstance(db_path, str) else DB_PATH
        self.db_path = os.path.join(db_path, f"{self.db_name}.db")

        self.driver = webdriver.Chrome(options=chrome_opt)
        self.driver.implicitly_wait(2)
        self.driver.get(self.url)
        self.conn, self.cursor = self.init_db()

        self.total_num_card = (
            num_card
            if num_card and isinstance(num_card, int) and num_card > 0
            else get_total_num_card(self.driver)
        )
        print(f"Total number of cards: {self.total_num_card}")
        self.total_num_page = (
            num_page
            if num_page and isinstance(num_page, int) and num_page > 0
            else get_total_num_page(self.driver)
        )
        print(f"Total number of pages: {self.total_num_page}")

        self.prodcut_crawler = PTCGProductCrawler()

    def __del__(self):
        self.driver.quit()
        self.conn.close()

    def __call__(
        self,
        start_page: int = 1,
        total_num_card: int = None,
        total_num_page: int = None,
        *args: Any,
        **kwds: Any,
    ) -> Any:

        total_num_card = (
            total_num_card if total_num_card else self.total_num_card
        )
        total_num_page = (
            total_num_page if total_num_page else self.total_num_page
        )

        # Extract card information
        pbar = tqdm(total=total_num_card)
        is_next = True
        card_count = 0
        page_number = 1
        while is_next:
            print(f"Page: {page_number}")
            list_items = find_elements(self.driver, By.CLASS_NAME, "List_item")

            if page_number < start_page:
                # Go to the next page by clicking the next page button
                # (the last item is the next page button)
                list_items = [list_items[-1]]

            for list_item in list_items:
                try:
                    # Get element
                    card_element = find_element(
                        list_item,
                        By.CSS_SELECTOR,
                        "li.List_item img[data-src]",
                    )

                    # Extract info from element
                    # e.g. /assets/images/card_images/large/SV2a/043491_P_ZENIGAME.jpg
                    data_src = card_element.get_attribute("data-src")
                    card_id = int(data_src.split("/")[-1].split("_")[0])
                    detail_info_url = f"https://www.pokemon-card.com/card-search/details.php/card/{card_id}/regu/XY"
                    detail_info = self.prodcut_crawler(detail_info_url)

                    # Update to db
                    self.insert_or_update_db(detail_info)

                    # Update progress bar
                    pbar.update(1)

                    # Check if the total number of cards is reached
                    card_count += 1
                    if card_count >= total_num_card:
                        is_next = False
                        break

                except StaleElementReferenceException:
                    # If the element is not found, try again
                    card_element = find_element(
                        list_item,
                        By.CSS_SELECTOR,
                        "li.List_item img[data-src]",
                    )
                    print("try again")
                    print(card_element.get_attribute("data-src"))
                except TimeoutException:
                    print("No card item found within the wait time")
                    try:
                        next_page_button = find_element(
                            list_item,
                            By.XPATH,
                            '//li[contains(.,"次のページ")]',
                        )
                        next_page_button.click()
                        print("Next page button found")
                        is_next = True
                    except TimeoutException:
                        print("No next page button found within the wait time")
                        is_next = False

            page_number += 1
            is_next = page_number < total_num_page

    def init_db(
        self,
    ) -> Tuple[sqlite3.Connection, sqlite3.Cursor]:
        """
        Initialize the database by creating a table if it doesn't exist.

        Args:
            db_name (str): The name of the database file.
            table_name (str): The name of the table to be created.
            is_drop_table (bool): Whether to drop the table if it already exists.

        Returns:
            sqlite3.Connection: The connection to the database.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        if self.is_drop_table:
            cursor.execute(f"""DROP TABLE IF EXISTS {self.table_name};""")
        cursor.execute(
            f"""CREATE TABLE IF NOT EXISTS {self.table_name}
                    (id INTEGER PRIMARY KEY,
                    card_type TEXT,
                    card_name_jp TEXT,
                    evo_type TEXT,
                    hp INT,
                    hp_type TEXT,
                    ability TEXT,
                    attacks TEXT,
                    special_rule TEXT,
                    weakness TEXT,
                    resistance TEXT,
                    retreat TEXT,
                    description_jp TEXT,
                    hash_unique_info TEXT UNIQUE,
                    card_code_jp TEXT,
                    img_url_jp TEXT,
                    rarity_code_jp TEXT
                    );"""
        )

        return conn, cursor

    def is_data_duplicated(self, row: List, cur_card_code: str) -> bool:
        """
        Check if the current card code is duplicated in the saved data.

        Args:
            row (List): The row of data containing the saved card code.
            cur_card_code (str): The current card code to check for duplication.

        Returns:
            bool: True if the current card code is duplicated, False otherwise.
        """
        card_code_index = NOT_UNIQUE_COLS.index("card_code_jp")
        saved_card_code = row[card_code_index]

        return cur_card_code in saved_card_code

    def insert_or_update_db(
        self,
        detail_info: Dict[str, Any],
        not_unique_cols: List[str] = NOT_UNIQUE_COLS,
    ) -> None:
        hash_unique_info = detail_info["hash_unique_info"]
        not_unique_cols_str = ", ".join(not_unique_cols)

        # Try to fetch the row with the given name
        self.cursor.execute(
            f"SELECT {not_unique_cols_str}\
                        FROM {self.table_name} WHERE hash_unique_info = ?",
            (hash_unique_info,),
        )
        row = self.cursor.fetchone()

        # If the row exists, update the data
        if row and not self.is_data_duplicated(
            row, detail_info["card_code_jp"]
        ):
            for index, col in enumerate(not_unique_cols):
                cur_list = json.loads(row[index])
                cur_list.append(detail_info[col])
                serialized = json.dumps(cur_list, ensure_ascii=False)
                self.cursor.execute(
                    f"UPDATE {self.table_name} SET {col} = ? WHERE hash_unique_info = ?",
                    (serialized, hash_unique_info),
                )
        else:
            # Serialize list type data
            for key, value in detail_info.items():
                if key in not_unique_cols:
                    value = [value]
                if isinstance(value, list):
                    detail_info[key] = json.dumps(value, ensure_ascii=False)

            # Insert a row of data
            columns = ", ".join(detail_info.keys())
            placeholders = ", ".join(["?"] * len(detail_info))
            sql = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders});"
            self.cursor.execute(sql, tuple(detail_info.values()))

        # Commit the changes
        self.conn.commit()


if __name__ == "__main__":
    builder = PTCGDatabaseBuilder(
        db_path="./", db_name="test", table_name="test", is_drop_table=True
    )
    builder(start_page=1, total_num_page=1, total_num_card=3)
    subprocess.run(
        [
            "python",
            "./scripts/read_db.py",
            "-db",
            f"./test.db",
            "-t",
            "test",
            "--limit",
            "10",
        ]
    )
