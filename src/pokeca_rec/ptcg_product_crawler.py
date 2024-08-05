import collections
import hashlib
import json
import re

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from pokeca_rec.utils.chrome_option import chrome_opt

EMPTY_STR = "NaN"
NOT_UNIQUE_COLS = ["card_code_jp", "img_url_jp", "rarity_code_jp"]


class PTCGProductCrawler:
    def __init__(self) -> None:
        """Extract card data showed in https://www.pokemon-card.com/card-search/index.php?&regulation_sidebar_form=XY"""  # noqa: E501
        self.url = None
        self.driver = None
        self.card_type_mapping_jp_en = {
            "ワザ": "pokemon",
            "グッズ": "tool",
            "ポケモンのどうぐ": "item",
            "スタジアム": "stadium",
            "サポート": "supporter",
            "基本エネルギー": "basic_energy",
            "特殊エネルギー": "special_energy",
        }
        self.card_type_mapping_en_jp = {
            value: key for key, value in self.card_type_mapping_jp_en.items()
        }
        self.evo_type_mapping_jp_en = {
            "たね": "basic",
            "1進化": "evo1",
            "2進化": "evo2",
            "V進化": "evoV",
        }
        self.evo_type_mapping_en_jp = {
            value: key for key, value in self.evo_type_mapping_jp_en.items()
        }
        self.valid_special_rule = set(
            [
                "ポケモンex",
                "ポケモンV",
                "ポケモンVMAX",
                "ポケモンVSTAR",
                "ポケモンV-UNION",
                "かがやくポケモン",
            ]
        )
        self.card_type = None
        self.img_url = None
        self.detail_info_keys = [
            "card_type",
            "card_name_jp",
            "evo_type",
            "hp",
            "hp_type",
            "ability",
            "attacks",
            "special_rule",
            "weakness",
            "resistance",
            "retreat",
            "description_jp",
            "hash_unique_info",
            "card_code_jp",
            "img_url_jp",
            "rarity_code_jp",
        ]

    def __call__(self, url: str):
        self.url = url
        detail_info = dict.fromkeys(self.detail_info_keys, EMPTY_STR)

        with webdriver.Chrome(options=chrome_opt) as driver:
            driver.implicitly_wait(2)
            driver.get(self.url)
            self.driver = driver

            # general
            detail_info["card_type"] = self._get_card_type()
            detail_info["card_name_jp"] = self._get_card_name()
            detail_info["img_url_jp"] = self._get_img_url()
            detail_info["card_code_jp"] = self._extract_card_code()
            detail_info["rarity_code_jp"] = self._extract_rarity_code()
            detail_info["description_jp"] = self._extract_desc()

            if detail_info["card_type"] == "pokemon":
                detail_info["evo_type"] = self._get_evo_type()
                detail_info["hp"] = self._get_pokemon_hp()
                detail_info["hp_type"] = self._extract_hp_type()
                detail_info["attacks"] = self._extract_attack()
                detail_info["ability"] = self._extract_ability()
                detail_info["special_rule"] = self._extract_special_rule()
                detail_info.update(self._extract_weak_resis_retreat())

        unique_vals = [
            value for key, value in detail_info.items() if key not in NOT_UNIQUE_COLS
        ]
        serialized = json.dumps(unique_vals, sort_keys=True, ensure_ascii=False)
        detail_info["hash_unique_info"] = hashlib.sha256(
            serialized.encode("utf-8")
        ).hexdigest()

        self.url = None
        self.driver = None
        self.card_type = None
        self.img_url = None
        return detail_info

    def _process_type_icon(self, type_icon_str):
        match = re.search(r"icon-(\w+)", type_icon_str)
        return match.group(1) if match else EMPTY_STR

    def _get_img_url(self):
        img_url = EMPTY_STR
        try:
            img_element = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((By.CLASS_NAME, "fit"))
            )
            img_url = img_element.get_attribute("src")
        except NoSuchElementException:
            img_url = EMPTY_STR

        self.img_url = img_url
        return img_url

    def _get_card_name(self):
        card_name = EMPTY_STR
        try:
            heading = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((By.CLASS_NAME, "Heading1.mt20"))
            )
            card_name = heading.text
        except NoSuchElementException:
            card_name = EMPTY_STR

        return card_name

    def _get_card_type(self):
        card_type = EMPTY_STR
        try:
            subheadings = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_all_elements_located((By.CLASS_NAME, "mt20"))
            )
            for subheading in subheadings:
                if subheading.text in self.card_type_mapping_jp_en:
                    card_type = self.card_type_mapping_jp_en.get(
                        subheading.text, EMPTY_STR
                    )
                    break
        except NoSuchElementException:
            card_type = EMPTY_STR

        self.card_type = card_type
        return card_type

    def _get_evo_type(self):
        pokemon_type = EMPTY_STR
        try:
            pokemon_type = self.driver.find_element(
                By.CSS_SELECTOR, ".type"
            ).text.replace(" ", "")
            pokemon_type = self.evo_type_mapping_jp_en.get(pokemon_type, EMPTY_STR)
        except NoSuchElementException:
            pokemon_type = EMPTY_STR

        return pokemon_type

    def _get_pokemon_hp(self):
        pokemon_hp = EMPTY_STR
        try:
            pokemon_hp = self.driver.find_element(By.CLASS_NAME, "hp-num").text
        except NoSuchElementException:
            pokemon_hp = EMPTY_STR

        return pokemon_hp

    def _extract_ability(self):
        ability_info = EMPTY_STR
        try:
            ability_header = self.driver.find_element(
                By.XPATH, "//h2[contains(text(), '特性')]"
            )
            ability_name = ability_header.find_element(
                By.XPATH, "following-sibling::h4"
            ).text
            ability_description = ability_header.find_element(
                By.XPATH, "following-sibling::p"
            ).text
            ability_info = f"{ability_name}: {ability_description}"
        except NoSuchElementException:
            ability_info = EMPTY_STR

        return ability_info

    def _extract_attack(self):
        output = []
        try:
            attack_elements = self.driver.find_elements(
                By.XPATH,
                "//h2[contains(text(), 'ワザ')]/following-sibling::h4",
            )
            for attack_element in attack_elements:
                attack_details = []

                # Extract the type icons
                attack_types = []
                icon_elements = attack_element.find_elements(
                    By.XPATH, ".//span[contains(@class, 'icon')]"
                )
                for icon_element in icon_elements:
                    icon_text = icon_element.get_attribute("class")
                    attack_types.append(self._process_type_icon(icon_text))
                attack_types = " ".join(attack_types)
                attack_details.append(attack_types)

                # Extract the attack name and damage
                attack_name_and_damage = attack_element.text.replace("\n", ", ")
                attack_details.append(attack_name_and_damage)

                # Extract the description from the next <p> tag
                description = attack_element.find_element(
                    By.XPATH, "following-sibling::p[1]"
                ).text.strip()
                attack_details.append(description)

                # Format and print the extracted details
                formatted_attack_detail = ", ".join(attack_details)
                output.append(formatted_attack_detail)
        except NoSuchElementException:
            output.append(EMPTY_STR)

        return output

    def _extract_hp_type(self):
        hp_type = EMPTY_STR
        try:
            hp_type_element = self.driver.find_element(
                By.XPATH, "//span[contains(text(), 'タイプ')]"
            )
            icon_element = hp_type_element.find_element(
                By.XPATH, "../span[contains(@class, 'icon')]"
            )
            icon_text = icon_element.get_attribute("class")
            hp_type = self._process_type_icon(icon_text)
        except NoSuchElementException:
            hp_type = EMPTY_STR

        return hp_type

    def _extract_card_code(self):
        card_code = EMPTY_STR
        try:
            if not self.img_url:
                self.img_url = self._get_img_url()

            if self.img_url == EMPTY_STR:
                return self.img_url

            product_code = self.img_url.split("/")[-2]
            subtext_element = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((By.CLASS_NAME, "subtext"))
            )
            card_code = subtext_element.text.strip().replace(" ", "")
            card_code = f"{product_code}-{card_code}"
        except NoSuchElementException:
            card_code = EMPTY_STR

        return card_code

    def _extract_rarity_code(self):
        rarity_code = EMPTY_STR
        try:
            rarity_icon_element = self.driver.find_element(
                By.XPATH, "//img[contains(@src, 'ic_rare')]"
            )
            src_value = rarity_icon_element.get_attribute("src")
            match = re.search(r"ic_rare_(.+?)\.gif", src_value)
            rarity_code = match.group(1) if match else EMPTY_STR
        except NoSuchElementException:
            rarity_code = EMPTY_STR

        return rarity_code

    def _extract_desc(self):
        description = EMPTY_STR
        if not self.card_type:
            self.card_type = self._get_card_type()

        if self.card_type == EMPTY_STR:
            return description

        try:
            if self.card_type == "pokemon":
                no_and_name = self.driver.find_element(By.CSS_SELECTOR, ".card h4").text
                height_and_weight = self.driver.find_element(
                    By.CSS_SELECTOR, ".card p:nth-of-type(1)"
                ).text
                description = self.driver.find_element(
                    By.CSS_SELECTOR, ".card p:nth-of-type(2)"
                ).text
                description = (
                    f"{no_and_name} {height_and_weight} {description}".replace(
                        "\u3000", " "
                    )
                )
            elif self.card_type in self.card_type_mapping_en_jp:
                map_card_type = self.card_type_mapping_en_jp[self.card_type]
                description = self.driver.find_element(
                    By.XPATH,
                    f"//h2[contains(text(), \
                        '{map_card_type}')]/following-sibling::p[1]",  # noqa: E501
                ).text  #TODO: add icon-* icon
                description = f"{description}".replace("\u3000", " ").replace("\n", "")
            else:
                raise ValueError
        except NoSuchElementException:
            description = EMPTY_STR
        except ValueError:
            print(f"Unknow card type: {self.card_type}")
            description = EMPTY_STR

        return description

    def _extract_special_rule(self):
        special_rule = EMPTY_STR
        try:
            special_rules_header = self.driver.find_element(
                By.XPATH, "//h2[contains(text(), '特別なルール')]"
            )
            paragraphs = special_rules_header.find_elements(
                By.XPATH, "following-sibling::p"
            )
            for paragraph in paragraphs:
                if paragraph.text in self.valid_special_rule:
                    special_rule = paragraph.text
        except NoSuchElementException:
            special_rule = EMPTY_STR

        return special_rule

    def _extract_weak_resis_retreat(self):
        data = {
            "weakness": EMPTY_STR,
            "resistance": EMPTY_STR,
            "retreat": EMPTY_STR,
        }

        table = self.driver.find_element(By.CSS_SELECTOR, "div.RightBox table")
        try:
            weakness = table.find_element(
                By.XPATH, ".//tr[2]/td[1]/span"
            ).get_attribute("class")
            weakness = self._process_type_icon(weakness)
            weakness += table.find_element(By.XPATH, ".//tr[2]/td[1]").text
            data["weakness"] = weakness
        except NoSuchElementException:
            pass

        try:
            resistance = table.find_element(
                By.XPATH, ".//tr[2]/td[2]/span"
            ).get_attribute("class")
            resistance = self._process_type_icon(resistance)
            resistance += table.find_element(By.XPATH, ".//tr[2]/td[2]").text
            data["resistance"] = resistance
        except NoSuchElementException:
            pass

        try:
            retreat = table.find_elements(
                By.XPATH, ".//tr[2]/td[3]/span[contains(@class, 'icon')]"
            )
            retreats = [
                self._process_type_icon(icon.get_attribute("class")) for icon in retreat
            ]
            retreats = dict(collections.Counter(retreats))
            retreats_str = ", ".join(
                f"{key}x{value}" for key, value in retreats.items()
            )
            data["retreat"] = retreats_str
        except NoSuchElementException:
            pass

        return data


if __name__ == "__main__":
    urls = [
        "https://www.pokemon-card.com/card-search/details.php/card/45186/regu/XY",  # pokemon # noqa: E501
        "https://www.pokemon-card.com/card-search/details.php/card/44501/regu/XY",  # tool # noqa: E501
        "https://www.pokemon-card.com/card-search/details.php/card/41298/regu/XY",  # stadium # noqa: E501
        "https://www.pokemon-card.com/card-search/details.php/card/42203/regu/XY",  # supporter # noqa: E501
        "https://www.pokemon-card.com/card-search/details.php/card/42183/regu/XY",  # item # noqa: E501
        "https://www.pokemon-card.com/card-search/details.php/card/44968/regu/XY",  # special energy # noqa: E501
        "https://www.pokemon-card.com/card-search/details.php/card/44950/regu/XY",  # basic energy # noqa: E501
    ]
    
    crawler = PTCGProductCrawler()

    for url in urls:
        detail_info = crawler(url)
        print(detail_info)
        print()
