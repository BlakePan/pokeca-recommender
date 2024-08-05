import sys
import argparse

sys.path.append(".")
from pokeca_rec.src.ptcg_db_builder import PTCGDatabaseBuilder


def main(args: argparse.Namespace):
    db_builder = PTCGDatabaseBuilder(
        db_path=args.db_path,
        db_name=args.db_name,
        table_name=args.table_name,
        is_drop_table=args.drop_table,
    )
    db_builder(
        start_page=args.start_page,
        total_num_card=args.num_cards,
        total_num_page=args.num_pages,
    )


if __name__ == "__main__":
    argparser = argparse.ArgumentParser(
        description="Build an SQLite database."
    )
    argparser.add_argument(
        "-p", "--db_path", help="Path to the SQLite database file."
    )
    argparser.add_argument(
        "-n", "--db_name", help="Name of the SQLite database."
    )
    argparser.add_argument(
        "-t", "--table_name", help="Name of the table to create."
    )
    argparser.add_argument(
        "--num_cards",
        type=int,
        help="Number of cards to insert into the database.",
    )
    argparser.add_argument(
        "--num_pages", type=int, help="Number of pages to crawl."
    )
    argparser.add_argument(
        "--start_page",
        type=int,
        default=1,
        help="Page to start crawling from.",
    )
    argparser.add_argument(
        "--drop_table",
        action="store_true",
        default=False,
        help="Drop the table before building the database.",
    )
    args = argparser.parse_args()
    main(args)
