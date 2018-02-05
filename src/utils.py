import logging.handlers
import json
import random
import re

import globals
import database
import wiki
import reddit

log = logging.getLogger("bot")


def getLinkToThread(threadID):
	return globals.SUBREDDIT_LINK + threadID


def startGame(initiator, opponent):
	log.debug("Creating new game between /u/{} and /u/{}".format(initiator, opponent))
	ID = database.getGameIDByCoach(initiator)
	if ID is not None:
		game = database.getGameByID(ID)
		if 'thread' in game:
			log.debug("Initiator has an existing game at {}".format(game['thread']))
			return False, "You're already playing a [game]({}).".format(getLinkToThread(game['thread']))
		else:
			log.debug("Replacing existing game request")
			database.deleteGameByID()

	ID = database.getGameIDByCoach(opponent)
	if ID is not None:
		game = database.getGameByID(ID)
		log.debug("Opponent has an existing game at {}".format(game['thread']))
		return False, "Your opponent is already playing a [game]({}).".format(getLinkToThread(game['thread']))

	gameID = database.createNewGame()
	database.addCoach(gameID, initiator, True)
	database.addCoach(gameID, opponent, False)

	return True, "Game created"


datatag = "[](#datatag"


def embedTableInMessage(message, table):
	return "{}{}{})".format(message, datatag, json.dumps(table))


def extractTableFromMessage(message):
	datatagLocation = message.find(datatag)
	if datatagLocation == -1:
		return None
	data = message[datatagLocation + len(datatag):-1]
	try:
		table = json.loads(data)
		return table
	except Exception:
		return None


def verifyCoaches(coaches):
	coachSet = set()
	for i, coach in enumerate(coaches):
		if coach in coachSet:
			return i, 'duplicate'
		coachSet.add(coach)

		team = wiki.getTeamByCoach(coach)
		if team is None:
			return i, 'team'

		game = database.getGameByCoach(coach)
		if game is not None:
			return i, 'game'

	return -1, None


def flair(team, flair):
	return "[{}](#f/{})".format(team, flair)


def renderTime(time):
	return str(time)


def renderDown(down):
	return str(down)


def renderGame(game):
	bldr = []

	bldr.append(flair(game['home']['name'], game['home']['tag']))
	bldr.append(" **")
	bldr.append(game['home']['name'])
	bldr.append("** @ ")
	bldr.append(flair(game['away']['name'], game['away']['tag']))
	bldr.append(" **")
	bldr.append(game['away']['name'])
	bldr.append("**\n\n___\n\n")

	for team in ['home', 'away']:
		bldr.append(flair(game[team]['name'], game[team]['tag']))
		bldr.append("\n\n")
		bldr.append("Total Passing Yards|Total Rushing Yards|Total Yards|Interceptions Lost|Fumbles Lost|Field Goals|Time of Possession\n")
		bldr.append(":-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:\n")
		bldr.append("{} yards|{} yards|{} yards|{}|{}|{}/{}|{}".format(
			game[team]['yardsPassing'],
			game[team]['yardsRushing'],
			game[team]['yardsTotal'],
			game[team]['turnoverInterceptions'],
			game[team]['turnoverFumble'],
			game[team]['fieldGoalsScored'],
			game[team]['fieldGoalsAttempted'],
			renderTime(game[team]['yardsPassing'])))
		bldr.append("\n\n___\n")

	bldr.append("Game Summary|Time\n")
	bldr.append(":-:|:-:\n")
	for drive in game['drives']:
		bldr.append("test|test\n")

	bldr.append("\n___\n\n")

	bldr.append("Playclock|Down|Ball Location|Possession\n")
	bldr.append(":-:|:-:|:-:|:-:|:-:\n")
	bldr.append(renderTime(game['status']['clock']))
	bldr.append("|")
	bldr.append(renderDown(game['status']['down']))
	bldr.append(" & ")
	bldr.append(str(game['status']['yards']))
	bldr.append("|")
	bldr.append(str(game['status']['location']))
	bldr.append("|")
	bldr.append(game[game['status']['possession']]['name'])

	bldr.append("\n\n___\n\n")

	bldr.append("Team|")
	numQuarters = len(game['score']['quarters'])
	for i in range(numQuarters):
		bldr.append("Q")
		bldr.append(str(i + 1))
		bldr.append("|")
	bldr.append("Total\n")
	bldr.append((":-:|"*(numQuarters + 2))[:-1])
	bldr.append("\n")
	for team in ['home', 'away']:
		bldr.append(flair(game[team]['name'], game[team]['tag']))
		bldr.append("|")
		for quarter in game['score']['quarters']:
			bldr.append(str(quarter[team]))
			bldr.append("|")
		bldr.append("**")
		bldr.append(str(game['score'][team]))
		bldr.append("**\n")

	return ''.join(bldr)


def coinToss():
	return random.choice([True, False])


def playNumber():
	return random.randint(0, 1500)


def getGameByThread(thread):
	threadText = reddit.getSubmission(thread).selftext
	return extractTableFromMessage(threadText)


def getGameByUser(user):
	dataGame = database.getGameByCoach(user)
	game = getGameByThread(dataGame['thread'])
	game['thread'] = dataGame['thread']
	return game


def getGameThreadText(game):
	threadText = renderGame(game)
	return embedTableInMessage(threadText, game)


def updateGameThread(game):
	if 'thread' not in game:
		log.error("No thread ID in game when trying to update")
	threadText = getGameThreadText(game)
	reddit.editThread(game['thread'], threadText)


def isCoachHome(game, coach):
	if coach.lower() in game['home']['coaches']:
		return True
	elif coach.lower() in game['away']['coaches']:
		return False
	else:
		return None


def sendGameMessage(isHome, game, message, dataTable):
	reddit.sendMessage(game[('home' if isHome else 'away')]['coaches'],
	                   "{} vs {}".format(game['home']['name'], game['away']['name']),
	                   embedTableInMessage(message, dataTable))


def newGameObject(home, away):
	status = {'clock': 15*60, 'quarter': 1, 'location': -1, 'possession': 'home', 'down': 1, 'yards': 10}
	score = {'quarters': [{'home': 0, 'away': 0}, {'home': 0, 'away': 0}, {'home': 0, 'away': 0}, {'home': 0, 'away': 0}], 'home': 0, 'away': 0}
	game = {'home': home, 'away': away, 'drives': [], 'status': status, 'score': score, 'waitingAction': 'coin', 'waitingOn': 'away'}
	return game


def reverseHomeAway(homeAway):
	if homeAway == 'home':
		return 'away'
	elif homeAway == 'away':
		return 'home'
	else:
		return None


def getRange(rangeString):
	rangeEnds = re.findall('(\d+)', rangeString)
	if len(rangeEnds) < 2 or len(rangeEnds) > 2:
		return None, None
	return int(rangeEnds[0]), int(rangeEnds[1])
