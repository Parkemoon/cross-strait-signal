import sqlite3
conn = sqlite3.connect('db/cross_strait_signal.db')
conn.execute("ALTER TABLE analyst_notes ADD COLUMN score_override REAL")
conn.commit()
print('Done')
conn.close()