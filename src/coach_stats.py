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


def getCoaches():
	c = dbConn.cursor()
	results = []
	for row in c.execute('''
		select Username,
			avg(Seconds),
			max(Created),
			count(*)
		from coach_stats
		group by Username
		'''):
		results.append({'username': row[0], 'seconds': row[1], 'latest': row[2], 'count': row[3]})

	return results


def delete_old_stats():
	c = dbConn.cursor()
	c.execute('''
		deleted from coach_stats
		where Created  <= date('now','-90 day')
	''')

	dbConn.commit()


def close():
	if dbConn is not None:
		dbConn.commit()
		dbConn.close()
