import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'cross_strait_signal.db')

def init_database():
    """Create the database and tables."""
    
    # Read the schema file
    schema_path = os.path.join(os.path.dirname(__file__), '..', 'db', 'schema.sql')
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = f.read()
    
    # Create database and run schema
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(schema)
    conn.close()
    
    print(f"Database created at: {DB_PATH}")

if __name__ == '__main__':
    init_database()