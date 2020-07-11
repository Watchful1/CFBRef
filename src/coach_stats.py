import sqlite3

dbConn = None


def init(database_name):
	global dbConn
	dbConn = sqlite3.connect(database_name)

	c = dbConn.cursor()
	c.execute('''
		CREATE TABLE IF NOT EXISTS coach_stats (
			ID INTEGER PRIMARY KEY AUTOINCREMENT,
			Username VARCHAR(80) NOT NULL,
			Seconds INTEGER,
			Created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
		)
	''')
	dbConn.commit()


def add_stat(username, lag_seconds):
	c = dbConn.cursor()
	c.execute('''
		INSERT INTO coach_stats
		(Username, Seconds)
		VALUES (?, ?)
	''', (username, lag_seconds))

	dbConn.commit()


def close():
	if dbConn is not None:
		dbConn.commit()
		dbConn.close()
