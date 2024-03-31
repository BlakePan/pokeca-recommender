import logging
import os
from typing import Any, Dict, List

from tinydb import Query, TinyDB

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


class DeckCategorizer:
    """Load deck category db to identify the category of input deck.
    If db is not exists, need to input deck recipes to build db first."""

    def __init__(
        self,
        deck_recipes: Dict = None,
        category_db_path: str = "db/deck_category.json",
    ):
        self.category_db_path = category_db_path
        self.category_db = None
        try:
            self.load()
            logger.info("Load category db Sucess!")
        except Exception as e:
            logger.info("Load category db Fail!")
            logger.info(str(e))
            logger.info("Build category db")
            self.init_category(deck_recipes)

    def __call__(self, deck: Dict, **kwds: Any) -> str:
        feature = self.preprocessing(deck)
        return self.get_category(feature)

    def _calculate_iou(
        self, feature1: List[str], feature2: List[str]
    ) -> float:
        set1 = set(feature1)
        set2 = set(feature2)
        intersection = set1.intersection(set2)
        union = set1.union(set2)
        iou = len(intersection) / len(union) if union else 0
        return iou

    def get_similarity(
        self, feature1: List[str], feature2: List[str]
    ) -> float:
        return self._calculate_iou(feature1, feature2)

    def get_category(self, feature: List[str]):
        """Return the closest category of input feature"""
        highest_sim = 0
        best_match_name = None

        for document in self.category_db.all():
            sim = self.get_similarity(feature, document["feature"])
            if sim > highest_sim:
                highest_sim = sim
                best_match_name = document["name"]

        return best_match_name

    def preprocessing(self, deck: Dict) -> List[str]:
        """Preprocessing on input deck to get feature
        v1: only use unique 'pokemon' name"""

        if deck.get("pokemons") is None:
            raise KeyError("deck missing key: 'pokemons'")
        feature = sorted(list(set(deck["pokemons"].keys())))
        return feature

    def get_intersection_cards(self, decks: List[Dict]) -> List[str]:
        intersection = set()
        for i, deck in enumerate(decks):
            if i == 0:
                intersection = set(self.preprocessing(deck))
            else:
                intersection &= set(self.preprocessing(deck))
        intersection = list(intersection)

        return intersection

    def transform_recipes_documents(
        self, deck_recipes: List[Dict[str, List]]
    ) -> List[Dict[str, List]]:
        """Transform deck recipes to db format: document"""
        documents = []
        for deck_recipe in deck_recipes:
            categ = list(deck_recipe.keys())[0]
            decks = deck_recipe[categ]
            feature = self.get_intersection_cards(decks)
            documents.append({"name": categ, "feature": feature})

        return documents

    def init_category(self, deck_recipes: List[Dict[str, List]]):
        """init and save category db to local"""
        self.category_db = TinyDB(
            self.category_db_path, indent=4, ensure_ascii=False
        )
        self.update(deck_recipes)

    def load(self):
        """load db from local db file"""
        self.category_db = TinyDB(
            self.category_db_path, indent=4, ensure_ascii=False
        )

    def update(self, deck_recipes: List[Dict[str, List]]):
        """update db from input deck recipes"""
        if self.category_db is None:
            self.init_category(deck_recipes)

        query = Query()
        documents = self.transform_recipes_documents(deck_recipes)
        for document in documents:
            # Search for a document with the same name
            search_result = self.category_db.search(
                query.name == document["name"]
            )

            if search_result:
                # If found, update the existing document with the new one
                self.category_db.update(
                    {"feature": document["feature"]},
                    query.name == document["name"],
                )
                logger.info(f"Updated feature with name: {document['name']}")
            else:
                # If not found, insert the new document
                self.category_db.insert(document)
                logger.info(
                    f"Inserted new feature with name: {document['name']}"
                )


if __name__ == "__main__":
    import json

    example_path = "assets/example_deck_recipies.json"
    with open(example_path, "r") as f:
        deck_recipes = json.load(f)

    categorizer = DeckCategorizer(deck_recipes)

    example_deck = {
        "energies": {"基本草エネルギー": 9, "基本鋼エネルギー": 5},
        "pokemons": {
            "かがやくゲッコウガ\nSVHK-006/053": 1,
            "コレクレー\nSV3a-020/062": 2,
            "コレクレー\nSV3a-021/062": 2,
            "サーフゴーex\nSV3a-050/062": 4,
            "チャデス\nSV5a-008/066": 2,
            "テツノイサハex\nSV5M-016/071": 1,
            "マナフィ\nSVHK-005/053": 1,
            "ヤバソチャex\nSV5a-009/066": 2,
        },
        "stadiums": {},
        "supporters": {
            "スイレンのお世話": 1,
            "ナタネの活気": 2,
            "ナンジャモ": 2,
            "フトゥー博士のシナリオ": 1,
            "ボスの指令": 2,
            "暗号マニアの解読": 2,
        },
        "tools": {
            "すごいつりざお": 1,
            "なかよしポフィン": 3,
            "エネルギー回収": 1,
            "カウンターキャッチャー": 1,
            "スーパーエネルギー回収": 4,
            "ネストボール": 2,
            "ハイパーボール": 3,
            "プライムキャッチャー": 1,
            "ポケモンいれかえ": 1,
            "ロストスイーパー": 1,
            "大地の器": 3,
        },
    }

    categorizer.update(deck_recipes)
    ret = categorizer(example_deck)
    print(ret)
