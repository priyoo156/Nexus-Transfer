import sqlite3

conn = sqlite3.connect('nexus.db')
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT UNIQUE NOT NULL,
    filename TEXT,
    original_filename TEXT,
    stored_filename TEXT,
    mode TEXT,
    copies INTEGER,
    total_pages INTEGER,
    total REAL,
    status TEXT DEFAULT 'Pending',
    uploaded_at TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute("PRAGMA table_info(orders)")
columns = {row[1] for row in cursor.fetchall()}

migrations = {
    "original_filename": "ALTER TABLE orders ADD COLUMN original_filename TEXT",
    "stored_filename": "ALTER TABLE orders ADD COLUMN stored_filename TEXT",
    "total_pages": "ALTER TABLE orders ADD COLUMN total_pages INTEGER",
    "uploaded_at": "ALTER TABLE orders ADD COLUMN uploaded_at TEXT",
    "created_at": "ALTER TABLE orders ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
}

for column, column_sql in migrations.items():
    if column not in columns:
        try:
            cursor.execute(column_sql)
        except sqlite3.Error:
            pass

conn.commit()
conn.close()

print("Database schema created successfully!")

