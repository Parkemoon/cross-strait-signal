import sqlite3
conn = sqlite3.connect('db/cross_strait_signal.db')
conn.execute("UPDATE sources SET is_active = 0 WHERE name = 'UDN'")
conn.commit()
print('Done')
conn.close()