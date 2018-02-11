import sqlite3

import globals

dbConn = None


def init():
	global dbConn
	dbConn = sqlite3.connect(globals.DATABASE_NAME)

	dbConn = sqlite3.connect(globals.DATABASE_NAME)
	c = dbConn.cursor()
	c.execute('''
		CREATE TABLE IF NOT EXISTS games (
			ID INTEGER PRIMARY KEY AUTOINCREMENT,
			ThreadID VARCHAR(80) NOT NULL,
			DefenseNumber INTEGER,
			LastPlayed TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
			UNIQUE (ThreadID)
		)
	''')
	c.execute('''
		CREATE TABLE IF NOT EXISTS coaches (
			ID INTEGER PRIMARY KEY AUTOINCREMENT,
			GameID INTEGER NOT NULL,
			Coach VARCHAR(80) NOT NULL,
			HomeTeam BOOLEAN NOT NULL,
			UNIQUE (Coach),
			FOREIGN KEY(GameID) REFERENCES games(ID)
		)
	''')
	dbConn.commit()


def close():
	dbConn.commit()
	dbConn.close()


def createNewGame(thread):
	c = dbConn.cursor()
	try:
		c.execute('''
			INSERT INTO games
			(ThreadID)
			VALUES (?)
		''', (thread,))
	except sqlite3.IntegrityError:
		return False

	dbConn.commit()

	return c.lastrowid


def addCoach(gameId, coach, home):
	c = dbConn.cursor()
	try:
		c.execute('''
			INSERT INTO coaches
			(GameID, Coach, HomeTeam)
			VALUES (?, ?, ?)
		''', (gameId, coach.lower(), home))
	except sqlite3.IntegrityError:
		return False

	dbConn.commit()
	return True


def getGameByCoach(coach):
	c = dbConn.cursor()
	result = c.execute('''
		SELECT g.ID
			,g.ThreadID
			,g.DefenseNumber
			,group_concat(c2.Coach) as Coaches
		FROM games g
			INNER JOIN coaches c
				ON g.ID = c.GameID
			LEFT JOIN coaches c2
				on g.ID = c2.GameID
		WHERE c.Coach = ?
		GROUP BY g.ID, g.ThreadID, g.DefenseNumber
	''', (coach.lower(),))

	resultTuple = result.fetchone()

	if not resultTuple:
		return None
	else:
		return {"id": resultTuple[0], "thread": resultTuple[1], "defenseNumber": resultTuple[2], "coaches": resultTuple[1].split(',')}


def getGameByID(id):
	c = dbConn.cursor()
	result = c.execute('''
		SELECT g.ThreadID
			,g.DefenseNumber
			,group_concat(c.Coach) as Coaches
		FROM games g
			LEFT JOIN coaches c
				ON g.ID = c.GameID
		WHERE g.ID = ?
		GROUP BY g.ThreadID, g.DefenseNumber
	''', (id,))

	resultTuple = result.fetchone()

	if not resultTuple:
		return None
	else:
		return {"id": id, "thread": resultTuple[0], "defenseNumber": resultTuple[1], "coaches": resultTuple[1].split(',')}


def deleteGameByID(id):
	c = dbConn.cursor()
	c.execute('''
		DELETE FROM games
		WHERE ID = ?
	''', (id,))
	dbConn.commit()

	if c.rowcount == 1:
		return True
	else:
		return False


def saveDefensiveNumber(gameID, number):
	c = dbConn.cursor()
	c.execute('''
		UPDATE games
		SET LastPlayed = CURRENT_TIMESTAMP
			,DefenseNumber = ?
		WHERE ID = ?
	''', (number, gameID))
	dbConn.commit()


def getDefensiveNumber(gameID):
	c = dbConn.cursor()
	result = c.execute('''
		SELECT DefenseNumber
		FROM games
		WHERE ID = ?
	''', (id,))

	resultTuple = result.fetchone()

	if not resultTuple:
		return None

	return resultTuple[0]


def clearDefensiveNumber(gameID):
	c = dbConn.cursor()
	c.execute('''
		UPDATE games
		SET LastPlayed = CURRENT_TIMESTAMP
			,DefenseNumber = NULL
		WHERE ID = ?
	''', (gameID,))
	dbConn.commit()


def setGamePlayed(gameID):
	c = dbConn.cursor()
	c.execute('''
		UPDATE games
		SET LastPlayed = CURRENT_TIMESTAMP
		WHERE ID = ?
	''', (gameID,))
	dbConn.commit()
