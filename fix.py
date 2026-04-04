import sqlite3
conn = sqlite3.connect('db/cross_strait_signal.db')
conn.execute('DELETE FROM ai_analysis')
conn.execute('DELETE FROM entities')
conn.execute('DELETE FROM keywords_matched')
conn.execute('DELETE FROM articles')
conn.commit()
print('Done')
conn.close()