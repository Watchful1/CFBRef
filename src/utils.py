import logging.handlers
import json
import random
import re
import math

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


def embedTableInMessage(message, table):
	return "{}{}{})".format(message, globals.datatag, json.dumps(table))


def extractTableFromMessage(message):
	datatagLocation = message.find(globals.datatag)
	if datatagLocation == -1:
		return None
	data = message[datatagLocation + len(globals.datatag):-1]
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
	return "{}:{}".format(str(math.trunc(time / 60)), str(time % 60).zfill(2))


def renderGame(game):
	bldr = []

	bldr.append(flair(game['away']['name'], game['away']['tag']))
	bldr.append(" **")
	bldr.append(game['away']['name'])
	bldr.append("** @ ")
	bldr.append(flair(game['home']['name'], game['home']['tag']))
	bldr.append(" **")
	bldr.append(game['home']['name'])
	bldr.append("**\n\n___\n\n")

	for team in ['away', 'home']:
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
	bldr.append(getDownString(game['status']['down']))
	bldr.append(" & ")
	bldr.append(str(game['status']['yards']))
	bldr.append("|")
	bldr.append(str(game['status']['location']))
	if game['status']['location'] < 50:
		bldr.append(" ")
		team = game[game['status']['possession']]
		bldr.append(flair(team['name'], team['tag']))
	elif game['status']['location'] > 50:
		bldr.append(" ")
		team = game[reverseHomeAway(game['status']['possession'])]
		bldr.append(flair(team['name'], team['tag']))
	bldr.append("|")
	team = game[game['status']['possession']]
	bldr.append(flair(team['name'], team['tag']))

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
	if dataGame is None:
		return None
	game = getGameByThread(dataGame['thread'])
	game['dataID'] = dataGame['id']
	game['thread'] = dataGame['thread']
	game['errored'] = dataGame['errored']
	game['waitingId'] = dataGame['waitingId']
	return game


def getGameThreadText(game):
	threadText = renderGame(game)
	return embedTableInMessage(threadText, game)


def updateGameThread(game):
	if 'thread' not in game:
		log.error("No thread ID in game when trying to update")
	game['dirty'] = False
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
	return reddit.getRecentSentMessage().id


def sendGameComment(game, message, dataTable):
	commentResult = reddit.replySubmission(game['thread'], embedTableInMessage(message, dataTable))
	game['waitingId'] = commentResult.fullname
	log.debug("Game comment sent, now waiting on: {}".format(game['waitingId']))


def getHomeAwayString(isHome):
	if isHome:
		return 'home'
	else:
		return 'away'


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


def isGameWaitingOn(game, user, action, messageId):
	if game['waitingAction'] != action:
		log.debug("Not waiting on {}: {}".format(action, game['waitingAction']))
		return "I'm not waiting on a {} for this game, are you sure you replied to the right message?".format(action)

	if (game['waitingOn'] == 'home') != isCoachHome(game, user):
		log.debug("Not waiting on message author's team")
		return "I'm not waiting on a message from you, are you sure you responded to the right message?"

	if game['waitingId'] is not None and game['waitingId'] != messageId:
		log.debug("Not waiting on message id: {} : {}".format(game['waitingId'], messageId))
		return "I'm not waiting on a reply to this message, be sure to respond to my newest message for this game."

	return None


def getCoachString(game, homeAway):
	bldr = []
	for coach in game[homeAway]['coaches']:
		bldr.append("/u/{}".format(coach))
	return " and ".join(bldr)


def getDownString(down):
	if down == 1:
		return "1st"
	elif down == 2:
		return "2nd"
	elif down == 3:
		return "3rd"
	elif down == 4:
		return "4th"
	else:
		log.warning("Hit a bad down number: {}".format(down))
		return ""


def getLocationString(location, offenseTeam, defenseTeam):
	if location < 0 or location > 100:
		log.warning("Bad location: {}".format(location))
		return str(location)

	if location == 0:
		return "{} goal line".format(offenseTeam)
	if location < 50:
		return "{} {}".format(offenseTeam, location)
	elif location == 50:
		return str(location)
	elif location == 100:
		return "{} goal line".format(defenseTeam)
	else:
		return "{} {}".format(defenseTeam, 100 - location)


def getCurrentPlayString(game):
	if game['status']['conversion']:
		return "{} just scored.".format(game[game['status']['possession']]['name'])
	else:
		return "It's {} and {} on the {}.".format(
			getDownString(game['status']['down']),
			"goal" if game['status']['location'] >= 90 else game['status']['yards'],
			getLocationString(game['status']['location'], game[game['status']['possession']]['name'], game[reverseHomeAway(game['status']['possession'])]['name'])
		)


def getWaitingOnString(game):
	string = "Error, no action"
	if game['waitingAction'] == 'coin':
		string = "Waiting on {} for coin toss".format(game[game['waitingOn']]['name'])
	elif game['waitingAction'] == 'defer':
		string = "Waiting on {} for receive/defer".format(game[game['waitingOn']]['name'])
	elif game['waitingAction'] == 'play':
		if game['waitingOn'] == game['status']['possession']:
			string = "Waiting on {} for an offensive play".format(game[game['waitingOn']]['name'])
		else:
			string = "Waiting on {} for an defensive number".format(game[game['waitingOn']]['name'])

	return string


def sendDefensiveNumberMessage(game):
	defenseHomeAway = reverseHomeAway(game['status']['possession'])
	log.debug("Sending get defence number to {}".format(getCoachString(game, defenseHomeAway)))
	messageResult = reddit.sendMessage(game[defenseHomeAway]['coaches'],
	                   "{} vs {}".format(game['away']['name'], game['home']['name']),
	                   embedTableInMessage("{}\n\nReply with a number between **1** and **1500**, inclusive."
	                                       .format(getCurrentPlayString(game)), {'action': 'play'}))
	game['waitingId'] = messageResult.fullname
	log.debug("Defensive number sent, now waiting on: {}".format(game['waitingId']))


def extractPlayNumber(message):
	numbers = re.findall('(\d+)', message)
	if len(numbers) < 1:
		log.debug("Couldn't find a number in message")
		return -1, "It looks like you should be sending me a number, but I can't find one in your message."
	if len(numbers) > 1:
		log.debug("Found more than one number")
		return -1, "It looks like you puts more than one number in your message"

	number = int(numbers[0])
	if number < 1 or number > 1500:
		log.debug("Number out of range: {}".format(number))
		return -1, "I found {}, but that's not a valid number.".format(number)

	return number, None


def setLogGameID(gameid):
	globals.logGameId = "{}: ".format(gameid)


def clearLogGameID():
	globals.logGameId = ""


def findKeywordInMessage(keywords, message):
	found = []
	for keyword in keywords:
		if isinstance(keyword, list):
			for actualKeyword in keyword:
				if actualKeyword in message:
					found.append(keyword[0])
					break
		else:
			if keyword in message:
				found.append(keyword)

	if len(found) == 0:
		return 'none'
	elif len(found) > 1:
		log.debug("Found multiple keywords: {}".format(', '.join(found)))
		return 'mult'
	else:
		return found[0]


def listSuggestedPlays(game):
	if game['status']['conversion']:
		return "**PAT** or **two point**"
	else:
		if game['status']['down'] == 4:
			if game['status']['location'] > 62:
				return "**field goal**, or go for it with **run** or **pass**"
			elif game['status']['location'] > 57:
				return "**punt** or **field goal**, or go for it with **run** or **pass**"
			else:
				return "**punt**, or go for it with **run** or **pass**"
		else:
			return "**run** or **pass**"



def newGameObject(home, away):
	status = {'clock': globals.quarterLength, 'quarter': 1, 'location': -1, 'possession': 'home', 'down': 1, 'yards': 10,
	          'timeouts': {'home': 3, 'away': 3}, 'requestedTimeout': {'home': 'none', 'away': 'none'}, 'conversion': False}
	score = {'quarters': [{'home': 0, 'away': 0}, {'home': 0, 'away': 0}, {'home': 0, 'away': 0}, {'home': 0, 'away': 0}], 'home': 0, 'away': 0}
	game = {'home': home, 'away': away, 'drives': [], 'status': status, 'score': score, 'errored': 0, 'waitingId': None,
	        'waitingAction': 'coin', 'waitingOn': 'away', 'dataID': -1, 'thread': "empty", "receivingNext": "home", 'dirty': False}
	return game
