import logging.handlers
import random
import re
import time
import copy
import requests
import json
import prawcore
from datetime import datetime
from datetime import timedelta

import static
import wiki
import reddit
import classes
import index
import string_utils
import file_utils
import drive_graphic
import counters
from classes import HomeAway
from classes import Action
from classes import Play
from classes import Result
from classes import QuarterType
from classes import DriveSummary

log = logging.getLogger("bot")


def error_is_transient(exception):
	return isinstance(exception, prawcore.exceptions.ServerError) or \
		isinstance(exception, prawcore.exceptions.ResponseException) or \
		isinstance(exception, prawcore.exceptions.RequestException) or \
		isinstance(exception, requests.exceptions.Timeout) or \
		isinstance(exception, requests.exceptions.ReadTimeout) or \
		isinstance(exception, requests.exceptions.RequestException)


def process_error(message, exception, traceback):
	is_transient = error_is_transient(exception)
	log.warning(f"{message}: {type(exception).__name__} : {exception}")
	if is_transient:
		log.info(traceback)
	else:
		log.warning(traceback)

	return is_transient


def postGameStartedMessage(game):
	log.debug("Game started, posting coin toss comment")
	message = "{}\n\n" \
			  "The game has started! {}, you're home. {}, you're away, call **heads** or **tails** in the air." \
		.format(wiki.intro, string_utils.getCoachString(game, True), string_utils.getCoachString(game, False))
	sendGameComment(game, message, getActionTable(game, Action.COIN))
	log.debug("Comment posted, now waiting on: {}".format(game.status.waitingId))


def startGameOvertime(game, tagTeams=False):
	log.debug("Starting overtime, posting coin toss comment")
	message = "Overtime has started! {}, you're away, call **heads** or **tails** in the air.\n\n{}".format(
		string_utils.getCoachString(game, False), string_utils.getCoachString(game, True) if tagTeams else '')
	comment = sendGameComment(game, message, getActionTable(game, Action.COIN))
	setWaitingId(game, comment.fullname)
	game.status.waitingAction = Action.COIN
	game.status.waitingOn = classes.HomeAway(False)


def startGame(homeTeam, awayTeam, startTime=None, location=None, station=None, homeRecord=None, awayRecord=None,
			  prefix=None, suffix=None, quarterLength=None, startOvertime=False):
	log.debug("Creating new game between {} and {}".format(homeTeam, awayTeam))

	result = verifyTeams([homeTeam, awayTeam])
	if result is not None:
		log.debug("Coaches not verified, {}".format(result))
		return "Something went wrong, someone is no longer an acceptable coach. Please try to start the game again"

	homeTeam = wiki.getTeamByTag(homeTeam.lower())
	awayTeam = wiki.getTeamByTag(awayTeam.lower())

	if startOvertime:
		quarter = 5
	else:
		quarter = 1
	game = newGameObject(homeTeam, awayTeam, quarterLength, quarter)
	if startTime is not None:
		game.startTime = startTime
	if location is not None:
		game.location = location
	if station is not None:
		game.station = station
	if homeRecord is not None:
		homeTeam.record = homeRecord
	if awayRecord is not None:
		awayTeam.record = awayRecord
	if prefix is not None:
		game.prefix = prefix
	if suffix is not None:
		game.suffix = suffix

	gameThread = string_utils.renderGame(game)
	gameTitle = "{} {}{} @ {}{}{}".format(
		"{}".format(string_utils.unescapeMarkdown(prefix)) if prefix is not None else "[GAME THREAD]",
		"{} ".format(string_utils.unescapeMarkdown(awayRecord)) if awayRecord is not None else "",
		game.away.name,
		"{} ".format(string_utils.unescapeMarkdown(homeRecord)) if homeRecord is not None else "",
		game.home.name,
		"{} ".format(string_utils.unescapeMarkdown(suffix)) if suffix is not None else "")

	threadID = str(reddit.submitSelfPost(static.SUBREDDIT, gameTitle, gameThread))
	game.thread = threadID
	log.debug("Game thread created: {}".format(threadID))

	index.addNewGame(game)

	for user in game.home.coaches:
		log.debug("Coach added to home: {}".format(user))
	for user in game.away.coaches:
		log.debug("Coach added to away: {}".format(user))

	if startOvertime:
		game.status.quarterType = QuarterType.OVERTIME_NORMAL
		startGameOvertime(game, tagTeams=True)
	else:
		postGameStartedMessage(game)
	updateGameThread(game)

	log.debug("Returning game started message")
	return "Game started between {} and {}. Find it [here]({}).".format(
		homeTeam.name,
		awayTeam.name,
		string_utils.getLinkToThread(threadID)
	)


def getActionTable(game, action):
	return {'action': action, 'thread': game.thread}


def verifyTeams(teamTags):
	teamSet = set()
	for i, tag in enumerate(teamTags):
		if tag in teamSet:
			log.debug("Teams are the same")
			return "You can't have a team play itself"
		teamSet.add(tag)

		team = wiki.getTeamByTag(tag)
		if team is None:
			homeAway = 'home' if i == 0 else 'away'
			log.debug("{} is not a valid team".format(homeAway))
			return "The {} team is not valid".format(homeAway)

		existingGame = index.getGameFromTeamTag(tag)
		if existingGame is not None:
			log.debug("{} is already in a game".format(tag))
			return "The team {} is already in a [game]({})".format(tag,
																   string_utils.getLinkToThread(existingGame.thread))

	return None


def paste_plays(game):
	method = "create" if game.playGist is None else "edit"

	if static.GIST_LIMITED and datetime.utcnow() < static.GIST_RESET:
		log.info(f"Gist update deferred till: {static.GIST_RESET}")
		counters.gist_event.labels(type="deferred", method=method).inc()
		static.GIST_PENDING.add(game.thread)
		game.gistUpdatePending = True
		return False

	if game.thread in static.GIST_PENDING:
		static.GIST_PENDING.remove(game.thread)

	play_string = string_utils.renderPlays(game)
	title = f"Play summary: {game.home.name} vs {game.away.name} : {game.thread}"
	base_url = 'https://api.github.com/gists'
	content = json.dumps({'files': {title: {"content": play_string}}})
	auth = requests.auth.HTTPBasicAuth(static.GIST_USERNAME, static.GIST_TOKEN)
	if game.playGist is not None:
		url = base_url + "/" + game.playGist
		result = requests.patch(url, data=content, auth=auth)
	else:
		url = base_url
		result = requests.post(url, data=content, auth=auth)

	ratelimit_remaining = int(result.headers['x-ratelimit-remaining'])
	counters.gist_ratelimit.labels(method=method).set(ratelimit_remaining)

	static.GIST_RESET = datetime.utcfromtimestamp(int(result.headers['x-ratelimit-reset']))
	if ratelimit_remaining <= 5:
		static.GIST_LIMITED = True
	else:
		static.GIST_LIMITED = False

	if result.ok:
		game.gistUpdatePending = False
		counters.gist_event.labels(type="success", method=method).inc()
		result_json = result.json()
		if 'id' not in result_json:
			log.warning("id not in gist response")
			return False
		log.info(f"Pasted to gist <{static.GIST_BASE_URL}{static.GIST_USERNAME}/{result_json['id']}> : {method} : {ratelimit_remaining}")
		game.playGist = result_json['id']
		return True
	else:
		static.GIST_PENDING.add(game.thread)
		game.gistUpdatePending = True
		counters.gist_event.labels(type="failure", method=method).inc()
		if game.playGist is not None:
			log.warning(f"Could not edit gist: {url} : {ratelimit_remaining}|{result.status_code} : {result.content} : <{static.GIST_BASE_URL}{static.GIST_USERNAME}/{game.playGist}>")
		else:
			log.warning(f"Could not post gist: {url} : {ratelimit_remaining}|{result.status_code} : {result.content} : {game.thread}")
		return False


def coinToss():
	return random.choice([True, False])


def playNumber():
	return random.randint(0, 1500)


def gameSortValue(game):
	return game.status.quarter * 1000 + game.status.clock


def updateGameThread(game):
	if game.thread is None:
		log.error("No thread ID in game when trying to update")
	game.dirty = False
	file_utils.saveGameObject(game)
	threadText = string_utils.renderGame(game)
	try:
		reddit.editThread(game.thread, threadText)
	except Exception as err:
		if error_is_transient(err):
			log.info("Transient error editing thread, waiting and trying again")
			time.sleep(10)
			reddit.editThread(game.thread, threadText)
		else:
			raise


def coachHomeAway(game, coach, checkPast=False):
	if coach.lower() in game.home.coaches:
		return HomeAway(True)
	elif coach.lower() in game.away.coaches:
		return HomeAway(False)

	if checkPast:
		if coach.lower() in game.home.pastCoaches:
			return HomeAway(True)
		elif coach.lower() in game.away.pastCoaches:
			return HomeAway(False)

	return None


def sendGameMessage(isHome, game, message, dataTable):
	reddit.sendMessage(game.team(isHome).coaches,
					   "{} vs {}".format(game.home.name, game.away.name),
					   string_utils.embedTableInMessage(message, dataTable))
	return reddit.getRecentSentMessage().id


def sendGameComment(game, message, dataTable=None, saveWaiting=True):
	commentResult = reddit.replySubmission(game.thread, string_utils.embedTableInMessage(message, dataTable))
	if saveWaiting:
		setWaitingId(game, commentResult.fullname)
	log.debug("Game comment sent, now waiting on: {}".format(game.status.waitingId))
	return commentResult


def getRange(rangeString):
	rangeEnds = re.findall('(\d+)', rangeString)
	if len(rangeEnds) < 2 or len(rangeEnds) > 2:
		return None, None
	return int(rangeEnds[0]), int(rangeEnds[1])


def getPrimaryWaitingId(waitingId):
	lastComma = waitingId.rfind(",")
	if lastComma == -1:
		return waitingId
	else:
		return waitingId[lastComma + 1:]


def clearReturnWaitingId(game):
	game.status.waitingId = re.sub(",?return", "", game.status.waitingId)


def resetWaitingId(game):
	game.status.waitingId = ""


def addWaitingId(game, waitingId):
	if game.status.waitingId == "":
		game.status.waitingId = waitingId
	else:
		game.status.waitingId = "{},{}".format(game.status.waitingId, waitingId)


def setWaitingId(game, waitingId):
	resetWaitingId(game)
	addWaitingId(game, waitingId)


def isGameWaitingOn(game, user, action, messageId, forceCoach=False):
	if game.status.waitingAction != action:
		log.debug("Not waiting on {}: {}".format(action.name, game.status.waitingAction.name))
		return "I'm not waiting on a '{}' for this game, are you sure you replied to the right message?".format(
			action.name.lower())

	if not forceCoach:
		if (game.status.waitingOn == 'home') != coachHomeAway(game, user):
			log.debug("Not waiting on message author's team")
			return "I'm not waiting on a message from you, are you sure you responded to the right message?"

	if messageId not in game.status.waitingId:
		log.debug("Not waiting on message id: {} : {}".format(game.status.waitingId, messageId))

		primaryWaitingId = getPrimaryWaitingId(game.status.waitingId)
		link = string_utils.getLinkFromGameThing(game.thread, primaryWaitingId)

		if messageId.startswith("t1"):
			messageType = "comment"
		elif messageId.startswith("t4"):
			messageType = "message"
		else:
			return "Something went wrong. Not valid: {}".format(primaryWaitingId)

		return "I'm not waiting on a reply to this {}. Please respond to this {}".format(messageType, link)

	return None


def sendDefensiveNumberMessage(game):
	defenseHomeAway = game.status.possession.negate()
	log.debug("Sending get defence number to {}".format(string_utils.getCoachString(game, defenseHomeAway)))
	results = reddit.sendMessage(
		recipients=game.team(defenseHomeAway).coaches,
		subject="{} vs {}".format(game.away.name, game.home.name),
		message=string_utils.embedTableInMessage(
			"{}\n\nReply with a number between **1** and **1500**, inclusive.\n\nYou have until {}."
			.format(
				string_utils.getCurrentPlayString(game),
				string_utils.renderDatetime(game.playclock)
			),
			getActionTable(game, game.status.waitingAction)
		)
	)
	resetWaitingId(game)
	for message in results:
		addWaitingId(game, message.fullname)
	log.debug("Defensive number sent, now waiting on: {}".format(game.status.waitingId))


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


def setLogGameID(threadId, game):
	static.game = game
	static.logGameId = " {}:".format(threadId)


def clearLogGameID():
	static.game = None
	static.logGameId = ""


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


def addStatRunPass(game, runPass, amount):
	if runPass == Play.RUN:
		addStat(game, 'yardsRushing', amount)
	elif runPass == Play.PASS:
		addStat(game, 'yardsPassing', amount)
	elif runPass == Play.PUNT:
		pass
	else:
		log.warning("Error in addStatRunPass, invalid play: {}".format(runPass))


def addStat(game, stat, amount, offenseHomeAway=None):
	if offenseHomeAway is None:
		offenseHomeAway = game.status.possession
	log.debug(
		"Adding stat {} : {} : {} : {}".format(stat, offenseHomeAway, getattr(game.status.stats(offenseHomeAway), stat),
											   amount))
	setattr(game.status.stats(offenseHomeAway), stat, getattr(game.status.stats(offenseHomeAway), stat) + amount)
	if stat in ['yardsPassing', 'yardsRushing']:
		game.status.stats(offenseHomeAway).yardsTotal += amount


def isGameOvertime(game):
	return game.status.quarterType in [QuarterType.OVERTIME_NORMAL, QuarterType.OVERTIME_TIME]


def cycleStatus(game, messageId, cyclePlaybooks=True):
	oldStatus = copy.deepcopy(game.status)
	oldStatus.messageId = messageId
	game.previousStatus.insert(0, oldStatus)
	if len(game.previousStatus) > 5:
		game.previousStatus.pop()

	if cyclePlaybooks:
		game.status.homePlaybook = game.home.playbook
		game.status.awayPlaybook = game.away.playbook


def revertStatus(game, index):
	game.status = game.previousStatus[index]


def newGameObject(home, away, quarterLength, quarter):
	return classes.Game(home, away, quarterLength, quarter)


def newDebugGameObject():
	home = classes.Team(tag="team1", name="Team 1", offense=classes.OffenseType.FLEXBONE,
						defense=classes.DefenseType.THREE_FOUR)
	home.coaches.append("watchful1")
	away = classes.Team(tag="team2", name="Team 2", offense=classes.OffenseType.SPREAD,
						defense=classes.DefenseType.FOUR_THREE)
	away.coaches.append("watchful12")
	return classes.Game(home, away)


def endGame(game, winner, postThread=True):
	game.status.quarterType = QuarterType.END
	game.status.waitingAction = Action.END
	game.status.winner = winner
	if game.status.down > 4:
		game.status.down = 4

	if postThread:
		postGameThread = string_utils.renderPostGame(game)
		winnerHome = True if game.status.winner == game.home.name else False
		gameTitle = "[POST GAME THREAD] {} defeats {}, {}-{}".format(
			game.team(winnerHome).name,
			game.team(not winnerHome).name,
			game.status.state(winnerHome).points,
			game.status.state(not winnerHome).points
		)
		threadID = str(reddit.submitSelfPost(static.SUBREDDIT, gameTitle, postGameThread))

		webhooks = static.get_webhook_for_conference(game.home.conference)
		if webhooks:
			discord_string = \
				f"{game.team(winnerHome).name} defeats {game.team(not winnerHome).name} " \
				f"{game.status.state(winnerHome).points}-{game.status.state(not winnerHome).points}"
			try:
				for webhook in webhooks:
					requests.post(webhook, data={"content": discord_string})
			except Exception:
				log.info(f"Unable to post to webhook")

		return "[Post game thread]({}).".format(string_utils.getLinkToThread(threadID))
	else:
		return None


def pauseGame(game, hours):
	game.playclock = datetime.utcnow() + timedelta(hours=hours + 18)
	game.deadline = game.deadline + timedelta(hours=hours + 18)


def setGamePlayed(game):
	game.playclock = datetime.utcnow() + timedelta(hours=18)
	game.playclockWarning = False


def addPlay(game, playSummary, forceDriveEndType):
	if len(game.status.plays[-1]) > 0:
		previousPlay = game.status.plays[-1][-1]
	else:
		previousPlay = None

	if forceDriveEndType is not None:
		if playSummary.result is None:
			playSummary.result = forceDriveEndType
		if playSummary.actualResult is None:
			playSummary.actualResult = forceDriveEndType

	if playSummary.actualResult in classes.driveEnders or \
			(previousPlay is not None and previousPlay.actualResult in classes.scoringResults and playSummary.actualResult in classes.postTouchdownEnders) or \
			forceDriveEndType is not None:
		game.status.plays[-1].append(playSummary)
		drive = game.status.plays[-1]
		game.status.plays.append([])

		summary = DriveSummary()
		for play in drive:
			if play.play in classes.movementPlays:
				if summary.posHome is None and play.result == Result.GAIN:
					summary.posHome = play.posHome
				if play.yards is not None:
					summary.yards += play.yards
				if play.playTime is not None:
					summary.time += play.playTime
				if play.runoffTime is not None:
					summary.time += play.runoffTime
		if drive[-1].actualResult in classes.postTouchdownEnders:
			summary.result = drive[-2].actualResult
		elif forceDriveEndType is not None:
			summary.result = forceDriveEndType
		else:
			summary.result = drive[-1].actualResult

		field = drive_graphic.makeField(drive)
		driveImageUrl = drive_graphic.uploadField(field, game.thread, str(len(game.status.plays) - 2))
		game.status.drives.append({'summary': summary, 'url': driveImageUrl})
		return f"Drive: [{str(summary)}]({driveImageUrl})"
	else:
		game.status.plays[-1].append(playSummary)
		return None
