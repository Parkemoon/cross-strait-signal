import sqlite3
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Scratch file for one-off DB operations.
# Write your query, run it, then clear this file again.

conn = sqlite3.connect('db/cross_strait_signal.db')
conn.row_factory = sqlite3.Row

# --- your query here ---

conn.close()
