import logging.handlers
import json
import random
import re
import math
from datetime import datetime
from datetime import timedelta

import globals
import database
import wiki
import reddit

log = logging.getLogger("bot")


def getLinkToThread(threadID):
	return globals.SUBREDDIT_LINK + threadID


def startGame(homeCoach, awayCoach, startTime=None, location=None, station=None, homeRecord=None, awayRecord=None):
	log.debug("Creating new game between /u/{} and /u/{}".format(homeCoach, awayCoach))

	coachNum, result = verifyCoaches([homeCoach, awayCoach])
	if coachNum != -1:
		log.debug("Coaches not verified, {} : {}".format(coachNum, result))
		return "Something went wrong, someone is no longer an acceptable coach. Please try to start the game again"

	homeTeam = wiki.getTeamByCoach(homeCoach.lower())
	awayTeam = wiki.getTeamByCoach(awayCoach.lower())
	for team in [homeTeam, awayTeam]:
		team['yardsPassing'] = 0
		team['yardsRushing'] = 0
		team['yardsTotal'] = 0
		team['turnoverInterceptions'] = 0
		team['turnoverFumble'] = 0
		team['fieldGoalsScored'] = 0
		team['fieldGoalsAttempted'] = 0
		team['posTime'] = 0
		team['record'] = None
		team['playclockPenalties'] = 0
		team['timeouts'] = 3
		team['requestedTimeout'] = 'none'

	game = newGameObject(homeTeam, awayTeam)
	if startTime is not None:
		game['startTime'] = startTime
	if location is not None:
		game['location'] = location
	if station is not None:
		game['station'] = station
	if homeRecord is not None:
		homeTeam['record'] = homeRecord
	if awayRecord is not None:
		awayTeam['record'] = awayRecord

	gameThread = getGameThreadText(game)
	gameTitle = "[GAME THREAD] {}{} @ {}{}".format(
		game['away']['name'],
		" {}".format(unescapeMarkdown(awayRecord)) if awayRecord is not None else "",
		game['home']['name'],
		" {}".format(unescapeMarkdown(homeRecord)) if homeRecord is not None else "")

	threadID = str(reddit.submitSelfPost(globals.SUBREDDIT, gameTitle, gameThread))
	game['thread'] = threadID
	log.debug("Game thread created: {}".format(threadID))

	gameID = database.createNewGame(threadID)
	game['dataID'] = gameID
	log.debug("Game database record created: {}".format(gameID))

	for user in game['home']['coaches']:
		database.addCoach(gameID, user, True)
		log.debug("Coach added to home: {}".format(user))
	for user in game['away']['coaches']:
		database.addCoach(gameID, user, False)
		log.debug("Coach added to away: {}".format(user))

	log.debug("Game started, posting coin toss comment")
	message = "The game has started! {}, you're home. {}, you're away, call **heads** or **tails** in the air.".format(getCoachString(game, 'home'), getCoachString(game, 'away'))
	sendGameComment(game, message, {'action': 'coin'})
	log.debug("Comment posted, now waiting on: {}".format(game['waitingId']))
	updateGameThread(game)

	log.debug("Returning game started message")
	return "Game started. Find it [here]({}).".format(getLinkToThread(threadID))


def embedTableInMessage(message, table):
	if table is None:
		return message
	else:
		return "{}{}{})".format(message, globals.datatag, json.dumps(table, default=str))


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
	teamSet = set()
	for i, coach in enumerate(coaches):
		if coach in coachSet:
			return i, 'duplicate'
		coachSet.add(coach)

		team = wiki.getTeamByCoach(coach)
		if team is None:
			return i, 'team'
		if team['name'] in teamSet:
			return i, 'same'
		teamSet.add(team['name'])

		game = database.getGameByCoach(coach)
		if game is not None:
			return i, 'game'

	return -1, None


markdown = [
	{'value': "[", 'result': "%5B"},
	{'value': "]", 'result': "%5D"},
	{'value': "(", 'result': "%28"},
	{'value': ")", 'result': "%29"},
]


def escapeMarkdown(value):
	for replacement in markdown:
		value = value.replace(replacement['value'], replacement['result'])
	return value


def unescapeMarkdown(value):
	for replacement in markdown:
		value = value.replace(replacement['result'], replacement['value'])
	return value


def flair(team):
	return "[{}](#f/{})".format(team['name'], team['tag'])


def renderTime(time):
	return "{}:{}".format(str(math.trunc(time / 60)), str(time % 60).zfill(2))


def renderGame(game):
	bldr = []

	bldr.append(flair(game['away']))
	bldr.append(" **")
	bldr.append(game['away']['name'])
	bldr.append("** @ ")
	bldr.append(flair(game['home']))
	bldr.append(" **")
	bldr.append(game['home']['name'])
	bldr.append("**\n\n")

	if game['startTime'] is not None:
		bldr.append(" **Game Start Time:** ")
		bldr.append(unescapeMarkdown(game['startTime']))
		bldr.append("\n\n")

	if game['location'] is not None:
		bldr.append(" **Location:** ")
		bldr.append(unescapeMarkdown(game['location']))
		bldr.append("\n\n")

	if game['station'] is not None:
		bldr.append(" **Watch:** ")
		bldr.append(unescapeMarkdown(game['station']))
		bldr.append("\n\n")


	bldr.append("\n\n")

	for team in ['away', 'home']:
		bldr.append(flair(game[team]))
		bldr.append("\n\n")
		bldr.append("Total Passing Yards|Total Rushing Yards|Total Yards|Interceptions Lost|Fumbles Lost|Field Goals|Time of Possession|Timeouts\n")
		bldr.append(":-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:\n")
		bldr.append("{} yards|{} yards|{} yards|{}|{}|{}/{}|{}|{}".format(
			game[team]['yardsPassing'],
			game[team]['yardsRushing'],
			game[team]['yardsTotal'],
			game[team]['turnoverInterceptions'],
			game[team]['turnoverFumble'],
			game[team]['fieldGoalsScored'],
			game[team]['fieldGoalsAttempted'],
			renderTime(game[team]['yardsPassing']),
			game[team]['timeouts']))
		bldr.append("\n\n___\n")

	bldr.append("Game Summary|Time\n")
	bldr.append(":-:|:-:\n")
	for drive in game['drives']:
		bldr.append("test|test\n")

	bldr.append("\n___\n\n")

	bldr.append("Playclock|Quarter|Down|Ball Location|Possession\n")
	bldr.append(":-:|:-:|:-:|:-:|:-:\n")
	bldr.append(renderTime(game['status']['clock']))
	bldr.append("|")
	bldr.append(str(game['status']['quarter']))
	bldr.append("|")
	bldr.append(getDownString(game['status']['down']))
	bldr.append(" & ")
	bldr.append(str(game['status']['yards']))
	bldr.append("|")
	if game['status']['location'] < 50:
		bldr.append(str(game['status']['location']))
		bldr.append(" ")
		team = game[game['status']['possession']]
		bldr.append(flair(team))
	elif game['status']['location'] > 50:
		bldr.append(str(100 - game['status']['location']))
		bldr.append(" ")
		team = game[reverseHomeAway(game['status']['possession'])]
		bldr.append(flair(team))
	else:
		bldr.append(str(game['status']['location']))
	bldr.append("|")
	team = game[game['status']['possession']]
	bldr.append(flair(team))

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
		bldr.append(flair(game[team]))
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
	return game


def getGameThreadText(game):
	threadText = renderGame(game)
	return embedTableInMessage(threadText, game)


def updateGameThread(game):
	updateGameTimes(game)
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


def sendGameComment(game, message, dataTable=None):
	commentResult = reddit.replySubmission(game['thread'], embedTableInMessage(message, dataTable))
	game['waitingId'] = commentResult.fullname
	log.debug("Game comment sent, now waiting on: {}".format(game['waitingId']))
	return commentResult


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

		if game['waitingId'].startswith("t1"):
			waitingMessageType = "comment"
			link = getLinkToThread(game['waitingId'][3:])
			link = "{}//{}".format(getLinkToThread(game['thread']), game['waitingId'][3:])
		elif game['waitingId'].startswith("t4"):
			waitingMessageType = "message"
			link = "{}{}".format(globals.MESSAGE_LINK, game['waitingId'][3:])
		else:
			return "Something went wrong. Not valid waiting: {}".format(game['waitingId'])

		if messageId.startswith("t1"):
			messageType = "comment"
		elif messageId.startswith("t4"):
			messageType = "message"
		else:
			return "Something went wrong. Not valid: {}".format(game['waitingId'])

		return "I'm not waiting on a reply to this {}. Please respond to this [{}]({})".format(messageType, waitingMessageType, link)

	return None


def getCoachString(game, homeAway):
	bldr = []
	for coach in game[homeAway]['coaches']:
		bldr.append("/u/{}".format(coach))
	return " and ".join(bldr)


def getNthWord(number):
	if number == 1:
		return "1st"
	elif number == 2:
		return "2nd"
	elif number == 3:
		return "3rd"
	elif number == 4:
		return "4th"
	else:
		return "{}th".format(number)


def getDownString(down):
	if down >= 1 and down <= 4:
		return getNthWord(down)
	else:
		log.warning("Hit a bad down number: {}".format(down))
		return "{}".format(down)


def getLocationString(game):
	location = game['status']['location']
	offenseTeam = game[game['status']['possession']]['name']
	defenseTeam = game[reverseHomeAway(game['status']['possession'])]['name']
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
	if game['waitingAction'] == 'conversion':
		return "{} just scored.".format(game[game['status']['possession']]['name'])
	elif game['waitingAction'] == 'kickoff':
		return "{} is kicking off".format(game[game['status']['possession']]['name'])
	else:
		return "It's {} and {} on the {}.".format(
			getDownString(game['status']['down']),
			"goal" if game['status']['location'] >= 90 else game['status']['yards'],
			getLocationString(game)
		)


def getWaitingOnString(game):
	string = "Error, no action"
	if game['waitingAction'] == 'coin':
		string = "Waiting on {} for coin toss".format(game[game['waitingOn']]['name'])
	elif game['waitingAction'] == 'defer':
		string = "Waiting on {} for receive/defer".format(game[game['waitingOn']]['name'])
	elif game['waitingAction'] == 'kickoff':
		string = "Waiting on {} for kickoff number".format(game[game['waitingOn']]['name'])
	elif game['waitingAction'] == 'play':
		if game['waitingOn'] == game['status']['possession']:
			string = "Waiting on {} for an offensive play".format(game[game['waitingOn']]['name'])
		else:
			string = "Waiting on {} for a defensive number".format(game[game['waitingOn']]['name'])

	return string


def sendDefensiveNumberMessage(game):
	defenseHomeAway = reverseHomeAway(game['status']['possession'])
	log.debug("Sending get defence number to {}".format(getCoachString(game, defenseHomeAway)))
	reddit.sendMessage(game[defenseHomeAway]['coaches'],
	                   "{} vs {}".format(game['away']['name'], game['home']['name']),
	                   embedTableInMessage("{}\n\nReply with a number between **1** and **1500**, inclusive."
	                                       .format(getCurrentPlayString(game)), {'action': game['waitingAction']}))
	messageResult = reddit.getRecentSentMessage()
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


def setLogGameID(threadId, gameId):
	globals.gameId = gameId
	globals.logGameId = " {}:".format(threadId)


def clearLogGameID():
	globals.gameId = None
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
	if game['waitingAction'] == 'conversion':
		return "**PAT** or **two point**"
	elif game['waitingAction'] == 'kickoff':
		return "**normal**, **squib** or **onside**"
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


def buildMessageLink(recipient, subject, content):
	return "https://np.reddit.com/message/compose/?to={}&subject={}&message={}".format(
		recipient,
		subject.replace(" ", "%20"),
		content.replace(" ", "%20")
	)


def addStatRunPass(game, runPass, amount):
	if runPass == 'run':
		addStat(game, 'yardsRushing', amount)
	elif runPass == 'pass':
		addStat(game, 'yardsPassing', amount)
	else:
		log.warning("Error in addStatRunPass, invalid play: {}".format(runPass))


def addStat(game, stat, amount, offenseHomeAway=None):
	if offenseHomeAway is None:
		offenseHomeAway = game['status']['possession']
	game[offenseHomeAway][stat] += amount
	if stat in ['yardsPassing', 'yardsRushing']:
		game[offenseHomeAway]['yardsTotal'] += amount


def isGameOvertime(game):
	return str.startswith(game['status']['quarterType'], 'overtime')


def updateGameTimes(game):
	game['playclock'] = database.getGamePlayed(game['dataID'])
	game['dirty'] = database.getGameDeadline(game['dataID'])


def newGameObject(home, away):
	status = {'clock': globals.quarterLength, 'quarter': 1, 'location': -1, 'possession': 'home', 'down': 1, 'yards': 10,
	          'quarterType': 'normal', 'overtimePossession': None}
	score = {'quarters': [{'home': 0, 'away': 0}, {'home': 0, 'away': 0}, {'home': 0, 'away': 0}, {'home': 0, 'away': 0}], 'home': 0, 'away': 0}
	game = {'home': home, 'away': away, 'drives': [], 'status': status, 'score': score, 'errored': 0, 'waitingId': None,
	        'waitingAction': 'coin', 'waitingOn': 'away', 'dataID': -1, 'thread': "empty", "receivingNext": "home",
	        'dirty': False, 'startTime': None, 'location': None, 'station': None, 'playclock': datetime.utcnow() + timedelta(hours=24),
	        'deadline': datetime.utcnow() + timedelta(days=10)}
	return game


# team = {'tag': items[0], 'name': items[1], 'offense': items[2].lower(), 'defense': items[3].lower(),
#         'coaches': []}
# team['yardsPassing'] = 0
# team['yardsRushing'] = 0
# team['yardsTotal'] = 0
# team['turnoverInterceptions'] = 0
# team['turnoverFumble'] = 0
# team['fieldGoalsScored'] = 0
# team['fieldGoalsAttempted'] = 0
# team['posTime'] = 0
# team['record'] = None
# team['playclockPenalties'] = 0
# team['timeouts'] = 3
# team['requestedTimeout'] = 'none'
