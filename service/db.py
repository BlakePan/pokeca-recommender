import sqlite3

DATABASE = 'db/ptcg_card.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    return conn

def query_autocomplete(text):
    conn = get_db()
    cursor = conn.cursor()
    query = "SELECT card_name_jp FROM ptcg_card WHERE card_name_jp LIKE ? LIMIT 10;"
    cursor.execute(query, (f'{text}%',))
    results = cursor.fetchall()
    conn.close()
    return [x[0] for x in results]
