import sqlite3

conn = sqlite3.connect("data/bot.db")
cursor = conn.cursor()

print("--- TESTS ---")
try:
    for row in cursor.execute("SELECT id, title, author_id, is_active FROM tests"):
        print("Test:", row)
except Exception as e:
    print("Error tests:", e)

print("--- USERS ---")
try:
    for row in cursor.execute("SELECT user_id, full_name, username FROM users"):
        print("User:", row)
except Exception as e:
    print("Error users:", e)

conn.close()
