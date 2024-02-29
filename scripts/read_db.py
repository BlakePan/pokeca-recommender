import argparse
import sqlite3


def main(database_path, table_name, limit=None):
    # Connect to the SQLite database
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    # Construct the SQL query with an optional limit
    sql_query = f"SELECT * FROM {table_name}"
    if limit is not None:
        sql_query += f" LIMIT {limit}"

    # Execute the query
    cursor.execute(sql_query)

    # Fetch and print the results
    rows = cursor.fetchall()
    for row in rows:
        print(row)
        print()

    # Close the database connection
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query an SQLite database.")
    parser.add_argument("-db", "--db_path", help="Path to the SQLite database file.")
    parser.add_argument("-t", "--table_name", help="Name of the table to query.")
    parser.add_argument(
        "--limit", type=int, help="Limit the number of output rows.", default=None
    )
    args = parser.parse_args()

    main(args.db_path, args.table_name, args.limit)
