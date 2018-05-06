import sqlite3
from datetime import datetime

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
			Deadline TIMESTAMP NOT NULL DEFAULT (DATETIME(CURRENT_TIMESTAMP, '+10 days')),
			Playclock TIMESTAMP NOT NULL DEFAULT (DATETIME(CURRENT_TIMESTAMP, '+24 hours')),
			Complete BOOLEAN NOT NULL DEFAULT 0,
			Errored BOOLEAN NOT NULL DEFAULT 0,
			UNIQUE (ThreadID)
		)
	''')
	c.execute('''
		CREATE TABLE IF NOT EXISTS coaches (
			ID INTEGER PRIMARY KEY AUTOINCREMENT,
			GameID INTEGER NOT NULL,
			Coach VARCHAR(80) NOT NULL,
			HomeTeam BOOLEAN NOT NULL,
			UNIQUE (Coach, GameID),
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
			,g.Errored
			,group_concat(c2.Coach) as Coaches
		FROM games g
			INNER JOIN coaches c
				ON g.ID = c.GameID
			LEFT JOIN coaches c2
				on g.ID = c2.GameID
		WHERE c.Coach = ?
			and g.Complete = 0
		GROUP BY g.ID, g.ThreadID
	''', (coach.lower(),))

	resultTuple = result.fetchone()

	if not resultTuple:
		return None
	else:
		return {'id': resultTuple[0], 'thread': resultTuple[1], 'errored': resultTuple[2] == 1,
		        'coaches': resultTuple[3].split(',')}


def getGameByID(id):
	c = dbConn.cursor()
	result = c.execute('''
		SELECT g.ThreadID
			,g.Errored
			,group_concat(c.Coach) as Coaches
		FROM games g
			LEFT JOIN coaches c
				ON g.ID = c.GameID
		WHERE g.ID = ?
			and g.Complete = 0
		GROUP BY g.ThreadID
	''', (id,))

	resultTuple = result.fetchone()

	if not resultTuple:
		return None
	else:
		return {'id': id, 'thread': resultTuple[0], 'errored': resultTuple[1] == 1,
		        'coaches': resultTuple[3].split(',')}


def endGame(threadId):
	c = dbConn.cursor()
	c.execute('''
		UPDATE games
		SET Complete = 1
			,Playclock = CURRENT_TIMESTAMP
		WHERE ThreadID = ?
	''', (threadId,))
	dbConn.commit()

	if c.rowcount == 1:
		return True
	else:
		return False


def unEndGame(threadId):
	c = dbConn.cursor()
	c.execute('''
		UPDATE games
		SET Complete = 0
			,Playclock = DATETIME(CURRENT_TIMESTAMP, '+24 hours')
		WHERE ThreadID = ?
	''', (threadId,))
	dbConn.commit()

	if c.rowcount == 1:
		return True
	else:
		return False


def pauseGame(threadID, hours):
	c = dbConn.cursor()
	c.execute('''
		UPDATE games
		SET Playclock = DATETIME(CURRENT_TIMESTAMP, '+' || ? || ' hours')
			,Deadline = DATETIME(Deadline, '+' || ? || ' hours')
		WHERE ThreadID = ?
	''', (str(hours), str(hours), threadID))
	dbConn.commit()


def setGamePlayed(gameID):
	c = dbConn.cursor()
	c.execute('''
		UPDATE games
		SET Playclock = DATETIME(CURRENT_TIMESTAMP, '+24 hours')
		WHERE ID = ?
	''', (gameID,))
	dbConn.commit()


def getGamePlayed(gameID):
	c = dbConn.cursor()
	result = c.execute('''
		SELECT Playclock
		FROM games
		WHERE ID = ?
	''', (gameID,))

	resultTuple = result.fetchone()

	if not resultTuple:
		return None

	return datetime.strptime(resultTuple[0], "%Y-%m-%d %H:%M:%S")


def getGameDeadline(gameID):
	c = dbConn.cursor()
	result = c.execute('''
		SELECT Deadline
		FROM games
		WHERE ID = ?
	''', (gameID,))

	resultTuple = result.fetchone()

	if not resultTuple:
		return None

	return datetime.strptime(resultTuple[0], "%Y-%m-%d %H:%M:%S")


def getGamesPastPlayclock():
	c = dbConn.cursor()
	results = []
	for row in c.execute('''
		SELECT ThreadID
		FROM games
		WHERE Playclock < CURRENT_TIMESTAMP
			and Complete = 0
			and Errored = 0
		'''):
		results.append(row[0])

	return results


def clearGameErrored(threadID):
	try:
		c = dbConn.cursor()
		c.execute('''
			UPDATE games
			SET Errored = 0
				,Deadline = DATETIME(Deadline, '+' || ((julianday(CURRENT_TIMESTAMP) - julianday(Playclock)) * 86400.0) || ' seconds')
				,Playclock = DATETIME(CURRENT_TIMESTAMP, '+24 hours')
			WHERE ThreadID = ?
				AND Errored = 1
		''', (threadID,))
		dbConn.commit()
	except Exception as err:
		return False
	return True


def setGameErrored(gameID):
	c = dbConn.cursor()
	c.execute('''
		UPDATE games
		SET Errored = 1
			,Playclock = CURRENT_TIMESTAMP
		WHERE ID = ?
	''', (gameID,))
	dbConn.commit()
