import logging.handlers
import re
import praw
import traceback
from datetime import datetime

import reddit
import utils
import wiki
import static
import state
import classes
import index
import string_utils
import file_utils
import coach_stats
from classes import Play
from classes import Action
from classes import TimeoutOption
from classes import TimeOption

log = logging.getLogger("bot")


def processMessageNewGame(body, author):
	log.debug("Processing new game message")
	results = []
	for line in body.split("\n"):
		teams = re.findall('(\w+)', line)
		if len(teams) < 3:
			log.debug("Could not find two teams in create game message")
			return "Please resend the message and specify two teams"

		homeTeam = teams[1]
		awayTeam = teams[2]
		log.debug("Found teams in message {} vs {}".format(homeTeam, awayTeam))

		result = utils.verifyTeams([homeTeam, awayTeam])

		if result is not None:
			return result

		startTime = None
		location = None
		station = None
		homeRecord = None
		awayRecord = None
		prefix = None
		suffix = None
		quarterLength = None

		for match in re.finditer(r'(?: )(\w+)(?:=")([^"]*)', line):
			if match.group(1) == "start":
				startTime = string_utils.escapeMarkdown(match.group(2))
				log.debug("Found start time: {}".format(startTime))
			elif match.group(1) == "location":
				location = string_utils.escapeMarkdown(match.group(2))
				log.debug("Found location: {}".format(location))
			elif match.group(1) == "station":
				station = string_utils.escapeMarkdown(match.group(2))
				log.debug("Found station: {}".format(station))
			elif match.group(1) == "homeRecord":
				homeRecord = string_utils.escapeMarkdown(match.group(2))
				log.debug("Found home record: {}".format(homeRecord))
			elif match.group(1) == "awayRecord":
				awayRecord = string_utils.escapeMarkdown(match.group(2))
				log.debug("Found away record: {}".format(awayRecord))
			elif match.group(1) == "prefix":
				prefix = string_utils.escapeMarkdown(match.group(2))
				log.debug("Found prefix: {}".format(prefix))
			elif match.group(1) == "suffix":
				suffix = string_utils.escapeMarkdown(match.group(2))
				log.debug("Found suffix: {}".format(suffix))
			elif match.group(1) == "length":
				try:
					quarterLength = int(match.group(2))
					log.debug("Found quarter length: {}".format(quarterLength))
				except Exception:
					log.warning("Could not parse quarter length argument: ".format(match.group(2)))

		results.append(utils.startGame(homeTeam, awayTeam, startTime, location, station, homeRecord, awayRecord, prefix, suffix, quarterLength))

	wiki.updateTeamsWiki()
	return '\n'.join(results)


def processMessageCoin(game, isHeads, author):
	log.debug("Processing coin toss message: {}".format(str(isHeads)))

	utils.setGamePlayed(game)
	if isHeads == utils.coinToss():
		log.debug("User won coin toss, asking if they want to defer")
		game.status.waitingAction = Action.DEFER
		game.status.waitingOn.set(False)
		utils.setWaitingId(game, 'return')
		game.dirty = True

		if utils.isGameOvertime(game):
			questionString = "do you want **defence** or **offense**?"
		else:
			questionString = "do you want to **receive** or **defer**?"
		message = "{}, {} won the toss, {}".format(string_utils.getCoachString(game, False), game.away.name, questionString)
		return True, string_utils.embedTableInMessage(message, utils.getActionTable(game, Action.DEFER))
	else:
		log.debug("User lost coin toss, asking other team if they want to defer")
		game.status.waitingAction = Action.DEFER
		game.status.waitingOn.set(True)
		utils.setWaitingId(game, 'return')
		game.dirty = True

		if utils.isGameOvertime(game):
			questionString = "do you want to **defence** or **offense**?"
		else:
			questionString = "do you want to **receive** or **defer**?"
		message = "{}, {} won the toss, {}".format(string_utils.getCoachString(game, True), game.home.name, questionString)
		return True, string_utils.embedTableInMessage(message, utils.getActionTable(game, Action.DEFER))


def processMessageDefer(game, isDefer, author, force=False):
	log.debug("Processing defer message: {}".format(str(isDefer)))

	authorHomeAway = utils.coachHomeAway(game, author, force)
	utils.setGamePlayed(game)
	if utils.isGameOvertime(game):
		if isDefer:
			log.debug("User deferred, {} is attacking".format(authorHomeAway.negate().name()))

			state.setStateOvertimeDrive(game, authorHomeAway.negate())
			game.status.receivingNext = authorHomeAway.copy()
			game.status.waitingOn.reverse()
			game.dirty = True
			utils.sendDefensiveNumberMessage(game)

			return True, "{} deferred and will attack next. Overtime has started!\n\n{}\n\n{}".format(
				game.team(authorHomeAway).name,
				string_utils.getCurrentPlayString(game),
				string_utils.getWaitingOnString(game))
		else:
			log.debug("User elected to attack, {} is attacking".format(authorHomeAway))

			state.setStateOvertimeDrive(game, authorHomeAway)
			game.status.receivingNext = authorHomeAway.negate()
			game.status.waitingOn.reverse()
			game.dirty = True
			utils.sendDefensiveNumberMessage(game)

			return True, "{} elected to attack. Overtime has started!\n\n{}\n\n{}".format(
				game.team(authorHomeAway).name,
				string_utils.getCurrentPlayString(game),
				string_utils.getWaitingOnString(game))
	else:
		if isDefer:
			log.debug("User deferred, {} is receiving".format(authorHomeAway.negate()))

			state.setStateKickoff(game, authorHomeAway)
			game.status.receivingNext = authorHomeAway.copy()
			game.status.waitingOn.reverse()
			game.dirty = True
			utils.sendDefensiveNumberMessage(game)

			return True, "{} deferred and will receive the ball in the second half. The game has started!\n\n{}\n\n{}".format(
				game.team(authorHomeAway).name,
				string_utils.getCurrentPlayString(game),
				string_utils.getWaitingOnString(game))
		else:
			log.debug("User elected to receive, {} is receiving".format(authorHomeAway))

			state.setStateKickoff(game, authorHomeAway.negate())
			game.status.receivingNext = authorHomeAway.negate()
			game.status.waitingOn.reverse()
			game.dirty = True
			utils.sendDefensiveNumberMessage(game)

			return True, "{} elected to receive. The game has started!\n\n{}\n\n{}".format(
				game.team(authorHomeAway).name,
				string_utils.getCurrentPlayString(game),
				string_utils.getWaitingOnString(game))


def processMessageDefenseNumber(game, message, author):
	log.debug("Processing defense number message")

	number, resultMessage = utils.extractPlayNumber(message)
	if resultMessage is not None:
		return False, resultMessage

	log.debug("Saving defense number: {}".format(number))
	game.status.defensiveNumber = number
	game.status.defensiveSubmitter = author

	timeoutMessage = None
	timeoutRequested = False
	if "timeout" in message:
		if game.status.state(game.status.possession.negate()).timeouts > 0:
			game.status.state(game.status.possession.negate()).requestedTimeout = TimeoutOption.REQUESTED
			timeoutMessage = "Timeout requested successfully"
			log.info("Defense requested a timeout")
			timeoutRequested = True
		else:
			timeoutMessage = "You requested a timeout, but you don't have any left"
			log.info("Defense requested a timeout, but didn't have any")

	game.status.waitingOn.reverse()
	game.dirty = True
	utils.setGamePlayed(game)

	log.debug("Sending offense play comment")
	resultMessage = "{} has submitted their number. {} you're up. You have until {}.\n\n{}\n\n{} reply with {} and your number. [Play list]({}){}{}".format(
		game.team(game.status.waitingOn.negate()).name,
		game.team(game.status.waitingOn).name,
		string_utils.renderDatetime(game.playclock),
		string_utils.getCurrentPlayString(game),
		string_utils.getCoachString(game, game.status.waitingOn),
		string_utils.listSuggestedPlays(game),
		"https://www.reddit.com/r/FakeCollegeFootball/wiki/refbot",
		"\n\nThe clock has stopped" if not game.status.timeRunoff else "",
		"\n\nThe defense requested a timeout" if timeoutRequested else ""
	)
	utils.sendGameComment(game, resultMessage, utils.getActionTable(game, game.status.waitingAction))

	result = ["I've got {} as your number.".format(number)]
	if timeoutMessage is not None:
		result.append(timeoutMessage)
	return True, '\n\n'.join(result)


def processMessageOffensePlay(game, message, author):
	log.debug("Processing offense number message")

	timeoutMessageOffense = None
	timeoutMessageDefense = None
	if "timeout" in message or "time out" in message:
		if game.status.state(game.status.possession).timeouts > 0:
			game.status.state(game.status.possession).requestedTimeout = TimeoutOption.REQUESTED
		else:
			timeoutMessageOffense = "The offense requested a timeout, but they don't have any left"

	normalOptions = ["run", "pass", "punt", "field goal", "kneel", "spike"]
	conversionOptions = ["two point", "pat", "kneel"]
	kickoffOptions = ["normal", "squib", "onside"]
	if game.status.waitingAction == Action.PLAY:
		playSelected = utils.findKeywordInMessage(normalOptions, message)
	elif game.status.waitingAction == Action.CONVERSION:
		playSelected = utils.findKeywordInMessage(conversionOptions, message)
	elif game.status.waitingAction == Action.KICKOFF:
		playSelected = utils.findKeywordInMessage(kickoffOptions, message)
	else:
		return False, "Something went wrong, invalid waiting action: {}".format(game.status.waitingAction)

	if playSelected == "run":
		play = Play.RUN
	elif playSelected == "pass":
		play = Play.PASS
	elif playSelected == "punt":
		play = Play.PUNT
	elif playSelected == "field goal":
		play = Play.FIELD_GOAL
	elif playSelected == "kneel":
		play = Play.KNEEL
	elif playSelected == "spike":
		play = Play.SPIKE
	elif playSelected == "two point":
		play = Play.TWO_POINT
	elif playSelected == "pat":
		if game.status.quarter >= 7:
			log.debug("Trying to pat after the 6th quarter")
			return False, "You cannot run a PAT after the second overtime"
		play = Play.PAT
	elif playSelected == "normal":
		play = Play.KICKOFF_NORMAL
	elif playSelected == "squib":
		play = Play.KICKOFF_SQUIB
	elif playSelected == "onside":
		if game.status.noOnside:
			log.debug("Trying to run an onside kick after a safety")
			return False, "You cannot run an onside kick after a safety"
		play = Play.KICKOFF_ONSIDE
	elif playSelected == "mult":
		log.debug("Found multiple plays")
		return False, "I found multiple plays in your message. Please repost it with just the play and number."
	else:
		log.debug("Didn't find any plays")
		return False, "I couldn't find a play in your message"

	if game.forceChew:
		timeOption = TimeOption.CHEW
	else:
		if play == Play.SPIKE:
			timeOption = TimeOption.HURRY
		else:
			timeOption = TimeOption.NORMAL
	if any(x in message for x in ['chew', 'chew the clock', 'milk the clock', 'chew clock']):
		timeOption = TimeOption.CHEW
	elif any(x in message for x in ['hurry up', 'no huddle', 'no-huddle', 'hurry']):
		timeOption = TimeOption.HURRY
	elif any(x in message for x in ['normal']):
		timeOption = TimeOption.NORMAL
	elif any(x in message for x in ['burn clock', 'final play']):
		timeOption = TimeOption.RUN

	number, numberMessage = utils.extractPlayNumber(message)
	if play not in classes.timePlays and number == -1:
		log.debug("Trying to execute a {} play, but didn't have a number".format(play))
		return False, numberMessage

	success, resultMessage = state.executePlay(
		game,
		play,
		number,
		timeOption,
		game.status.waitingAction == Action.CONVERSION,
		author
	)

	if game.status.state(game.status.possession).requestedTimeout == TimeoutOption.USED:
		timeoutMessageOffense = "The offense is charged a timeout"
	elif game.status.state(game.status.possession).requestedTimeout == TimeoutOption.REQUESTED:
		timeoutMessageOffense = "The offense requested a timeout, but it was not used"
	game.status.state(game.status.possession).requestedTimeout = TimeoutOption.NONE

	if game.status.state(game.status.possession.negate()).requestedTimeout == TimeoutOption.USED:
		timeoutMessageDefense = "The defense was charged a timeout"
	elif game.status.state(game.status.possession.negate()).requestedTimeout == TimeoutOption.REQUESTED:
		timeoutMessageDefense = "The defense requested a timeout, but it was not used"
	game.status.state(game.status.possession.negate()).requestedTimeout = TimeoutOption.NONE

	result = [resultMessage]
	if timeoutMessageOffense is not None:
		result.append(timeoutMessageOffense)
	if timeoutMessageDefense is not None:
		result.append(timeoutMessageDefense)

	if not game.status.timeRunoff:
		result.append("The clock is stopped.")

	game.status.waitingOn.reverse()

	result.append(string_utils.getCoachString(game, game.status.waitingOn))

	game.dirty = True
	utils.setGamePlayed(game)
	if game.status.waitingAction in classes.playActions:
		utils.sendDefensiveNumberMessage(game)
	elif game.status.waitingAction == Action.OVERTIME:
		log.debug("Starting overtime, posting coin toss comment")
		message = "Overtime has started! {}, you're away, call **heads** or **tails** in the air.".format(
			string_utils.getCoachString(game, False))
		comment = utils.sendGameComment(game, message, utils.getActionTable(game, Action.COIN))
		utils.setWaitingId(game, comment.fullname)
		game.status.waitingAction = Action.COIN
		game.status.waitingOn = classes.HomeAway(False)

	return success, string_utils.embedTableInMessage('\n\n'.join(result), utils.getActionTable(game, game.status.waitingAction))


def reprocessPlay(game, messageId, isRerun=False):
	log.debug("Reprocessing message/comment: {}".format(messageId))
	if messageId == "DelayOfGame":
		state.executeDelayOfGame(game)
	else:
		message = reddit.getThingFromFullname(messageId)
		if message is None:
			return "Something went wrong. Not valid fullname: {}".format(messageId)
		processMessage(message, True, isRerun)
	return "Reprocessed message: {}".format(messageId)


def processMessageKickGame(body):
	log.debug("Processing kick game message")
	threadIds = re.findall('([\da-z]{6})', body)
	if len(threadIds) < 1:
		log.debug("Couldn't find a thread id in message")
		return "Couldn't find a thread id in message"
	log.debug("Found thread id: {}".format(threadIds[0]))

	game = index.reloadAndReturn(threadIds[0], alwaysReturn=True)
	if game is None:
		return "Game not found: {}".format(threadIds[0])

	index.clearGameErrored(game)
	file_utils.saveGameObject(game)
	result = ["Kicked game: {}".format(threadIds[0])]

	statusIndex = re.findall('(?:revert:)(\d+)', body)
	if len(statusIndex) > 0:
		log.debug("Reverting to status: {}".format(statusIndex[0]))
		utils.revertStatus(game, int(statusIndex[0]))
		file_utils.saveGameObject(game)
		result.append("Reverted to status: {}".format(statusIndex[0]))

	messageFullname = re.findall('(?:message:)(t\d_[\da-z]{6,})', body)
	if len(messageFullname) > 0:
		result.append(reprocessPlay(game, messageFullname[0]))

	log.debug("Finished kicking game")
	return '\n\n'.join(result)


def processMessagePauseGame(body):
	log.debug("Processing pause game message")
	threadIds = re.findall('([\da-z]{6})', body)
	if len(threadIds) < 1:
		log.debug("Couldn't find a thread id in message")
		return "Couldn't find a thread id in message"
	log.debug("Found thread id: {}".format(threadIds[0]))

	hours = re.findall(r'(\b\d{1,3}\b)', body)
	if len(hours) < 1:
		log.debug("Couldn't find a number of hours in message")
		return "Couldn't find a number of hours in message"
	log.debug("Found hours: {}".format(hours[0]))

	game = index.reloadAndReturn(threadIds[0])
	utils.pauseGame(game, int(hours[0]))
	file_utils.saveGameObject(game)

	return "Game {} paused for {} hours".format(threadIds[0], hours[0])


def processMessageAbandonGame(body):
	log.debug("Processing abandon game message")
	threadIds = re.findall('(?: )([\da-z]{6})', body)
	if len(threadIds) < 1:
		log.debug("Couldn't find a thread id in message")
		return "Couldn't find a thread id in message"
	log.debug("Found thread id: {}".format(threadIds[0]))

	game = index.reloadAndReturn(threadIds[0], True)
	if game is None:
		return "Game not found: {}".format(threadIds[0])

	utils.endGame(game, "Abandoned", False)
	utils.updateGameThread(game)
	file_utils.saveGameObject(game)
	index.endGame(game)

	return "Game {} abandoned".format(threadIds[0])


def processMessageGameStatus(body):
	log.debug("Processing game status message")
	threadIds = re.findall('(?: )([\da-z]{6})', body)
	if len(threadIds) < 1:
		log.debug("Couldn't find a thread id in message")
		return "Couldn't find a thread id in message"
	log.debug("Found thread id: {}".format(threadIds[0]))

	game = file_utils.loadGameObject(threadIds[0])
	if game is None:
		return "Game {} doesn't exist".format(threadIds[0])
	else:
		return string_utils.renderGameStatusMessage(game)


def processMessageReindex(body):
	log.debug("Processing reindex message")
	wiki.loadPages(True)
	index.init()
	return "Wiki pages reloaded and games reindexed"


def processMessageDefaultChew(body):
	log.debug("Processing default chew message")
	threadIds = re.findall('(?: )([\da-z]{6})', body)
	if len(threadIds) < 1:
		log.debug("Couldn't find a thread id in message")
		return "Couldn't find a thread id in message"
	log.debug("Found thread id: {}".format(threadIds[0]))

	game = file_utils.loadGameObject(threadIds[0])
	if game is None:
		return "Game not found: {}".format(threadIds[0])

	if "normal" in body:
		game.forceChew = False
		result = "Game changed to normal plays by default: {}".format(threadIds[0])
	else:
		game.forceChew = True
		result = "Game changed to chew the clock plays by default: {}".format(threadIds[0])

	utils.updateGameThread(game)
	file_utils.saveGameObject(game)

	return result


def processMessageGameList(body):
	log.debug("Processing game list message")

	bldr = ['Teams|Link|Quarter|Clock\n:-:|:-:|:-:|:-:\n']
	games = index.getAllGames()
	log.debug("Listing {} games".format(len(games)))
	for game in games:
		bldr.append(game.away.name)
		bldr.append(" vs ")
		bldr.append(game.home.name)
		bldr.append("|[Link](")
		bldr.append(string_utils.getLinkToThread(game.thread))
		bldr.append(")|")
		bldr.append(str(game.status.quarter))
		bldr.append("|")
		bldr.append(string_utils.renderTime(game.status.clock))
		bldr.append("\n")

	return ''.join(bldr)


def processMessageSuggestion(body, subject):
	stringKey = re.findall(r'(?:suggestion )(\w+)', subject)
	if len(stringKey) < 1:
		log.debug("Couldn't find a suggestion key in subject")
		return "I couldn't figure out what key you were suggesting for. Please make sure the subject line is correct"

	file_utils.saveStringSuggestion(stringKey[0], body)

	return "Thanks! I'll manually review all suggestions and add the good ones."


def processMessageTeams(body, subject):
	bldr = []
	for teamLine in body.splitlines():
		team, result = wiki.parseTeamLine(teamLine)
		if team is None:
			bldr.append(result)
			bldr.append("  \n")
			continue

		if team.tag in wiki.teams:
			log.debug(f"Updated team: {team.tag}")
			bldr.append(f"Updated team: {team.tag}")
			wiki.teams[team.tag] = team

			game = index.getGameFromTeamTag(team.tag)
			if game is not None:
				try:
					if len(game.previousStatus):
						log.debug("Reverting status and reprocessing {}".format(game.previousStatus[0].messageId))
						utils.revertStatus(game, 0)
						file_utils.saveGameObject(game)
						reprocessPlay(game, game.status.messageId)
						bldr.append(" and reprocessed last play")
					else:
						log.info("Coaches changed, but game has no plays, not reprocessing")

				except Exception as err:
					log.warning(traceback.format_exc())
					log.warning("Unable to revert game when changing coaches")
					bldr.append(" something went wrong reprocessing the last play")

		else:
			log.debug(f"Added team: {team.tag}")
			bldr.append(f"Added team: {team.tag}")
			wiki.teams[team.tag] = team
		bldr.append("  \n")

	wiki.updateTeamsWiki()
	file_utils.saveTeams(wiki.teams)

	return ''.join(bldr)


def processMessageRestartGame(body):
	log.debug("Processing restart game message")
	threadIdGroup = re.search(r'(?: )([\da-z]{6})', body)
	if not threadIdGroup:
		log.debug("Couldn't find a thread id in message")
		return "Couldn't find a thread id in message"
	threadId = threadIdGroup.group(1)
	log.debug("Found thread id: {}".format(threadId))

	game = file_utils.loadGameObject(threadId)
	if game is None:
		log.info(f"Couldn't load game {threadId}")
		return "Game not found: {}".format(threadId)

	reasonGroup = re.search(r'(?: [\da-z]{6} )(.*)', body)
	if not reasonGroup or reasonGroup.group(1) == "Replace this with the reason you need to restart the game":
		log.debug("Couldn't find a restart reason")
		return "Couldn't find a restart reason in the message. Please include one after the thread id."
	file_utils.saveRestartReason(threadId, reasonGroup.group(1))

	bldr = []
	bldr.append(f"Game {threadId} abandoned.\n\n")
	log.debug("Abandoning game")
	utils.endGame(game, "Abandoned", False)
	utils.updateGameThread(game)
	file_utils.saveGameObject(game)
	index.endGame(game)

	bldr.append(utils.startGame(
		game.home.tag,
		game.away.tag,
		game.startTime,
		game.location,
		game.station,
		game.home.record,
		game.home.record,
		game.prefix,
		game.suffix))

	return ''.join(bldr)


def processMessageRerunLastPlay(body):
	log.debug("Processing rerun play message")
	threadIdGroup = re.search(r'(?: )([\da-z]{6})', body)
	if not threadIdGroup:
		log.debug("Couldn't find a thread id in message")
		return "Couldn't find a thread id in message"
	threadId = threadIdGroup.group(1)
	log.debug("Found thread id: {}".format(threadId))

	game = file_utils.loadGameObject(threadId)
	if game is None:
		log.info(f"Couldn't load game {threadId}")
		return f"Game not found: {threadId}"

	if game.playRerun:
		log.info("Game has already been rerun")
		return f"The last play has already been rerun. If the game is still broken, please ping {static.OWNER} in discord"

	try:
		if len(game.previousStatus):
			log.debug("Reverting status and reprocessing {}".format(game.previousStatus[0].messageId))
			utils.revertStatus(game, 0)
			file_utils.saveGameObject(game)
			reprocessPlay(game, game.status.messageId, True)
		else:
			log.info("Game has no plays")
			return "Game has no plays"

	except Exception as err:
		log.warning(traceback.format_exc())
		log.warning("Unable to revert game")
		return "Something went wrong reprocessing the last play"

	return f"Reran last play for game {threadId}"


def processMessage(message, reprocess=False, isRerun=False):
	if isinstance(message, praw.models.Message):
		isMessage = True
		log.debug("Processing a message from /u/{} : {}".format(str(message.author), message.id))
	else:
		isMessage = False
		log.debug("Processing a comment from /u/{} : {}".format(str(message.author), message.id))

	response = None
	success = None
	updateWaiting = True
	dataTable = None

	if message.parent_id is not None and (message.parent_id.startswith("t1") or message.parent_id.startswith("t4")):
		if isMessage:
			parent = reddit.getMessage(message.parent_id[3:])
		else:
			parent = reddit.getComment(message.parent_id[3:])

		if parent is not None and str(parent.author).lower() == static.ACCOUNT_NAME:
			dataTable = string_utils.extractTableFromMessage(parent.body)
			if dataTable is not None:
				if 'action' not in dataTable or 'thread' not in dataTable:
					dataTable = None
				else:
					dataTable['source'] = parent.fullname
					log.debug("Found a valid datatable in parent message: {}".format(str(dataTable)))

			seconds_lag = (datetime.utcfromtimestamp(message.created_utc) - datetime.utcfromtimestamp(parent.created_utc)).total_seconds()
			log.debug(f"Saving reply lag of {seconds_lag} for u/{message.author.name}")
			coach_stats.add_stat(message.author.name, seconds_lag)

	body = message.body.lower()
	author = str(message.author)
	game = None
	appendMessageId = False
	if dataTable is not None:
		game = index.reloadAndReturn(dataTable['thread'])
		if game is not None:
			utils.cycleStatus(game, message.fullname, not reprocess)
			utils.setLogGameID(game.thread, game)

			waitingOn = utils.isGameWaitingOn(game, author, dataTable['action'], dataTable['source'], reprocess)
			if waitingOn is not None:
				response = waitingOn
				success = False
				updateWaiting = False

			elif game.errored:
				log.debug("Game is errored, skipping")
				response = "This game is currently in an error state, /u/{} has been contacted to take a look".format(
					static.OWNER)
				success = False
				updateWaiting = False

			else:
				game.playRerun = isRerun
				if dataTable['action'] == Action.COIN and not isMessage:
					keywords = ["heads", "tails"]
					keyword = utils.findKeywordInMessage(keywords, body)
					if keyword == "heads":
						success, response = processMessageCoin(game, True, author)
					elif keyword == "tails":
						success, response = processMessageCoin(game, False, author)
					elif keyword == "mult":
						success = False
						response = "I found both {} in your message. Please reply with just one of them.".format(
							' and '.join(keywords))

				elif dataTable['action'] == Action.DEFER and not isMessage:
					if utils.isGameOvertime(game):
						keywords = ["defense", "defence", "offense"]
					else:
						keywords = ["defer", "receive"]
					keyword = utils.findKeywordInMessage(keywords, body)
					if keyword == "defer" or keyword == "defense" or keyword == "defence":
						success, response = processMessageDefer(game, True, author, reprocess)
					elif keyword == "receive" or keyword == "offense":
						success, response = processMessageDefer(game, False, author, reprocess)
					elif keyword == "mult":
						success = False
						response = "I found both {} in your message. Please reply with just one of them.".format(
							' and '.join(keywords))

				elif dataTable['action'] in classes.playActions and isMessage:
					success, response = processMessageDefenseNumber(game, body, author)
					appendMessageId = not success

				elif dataTable['action'] in classes.playActions and not isMessage:
					success, response = processMessageOffensePlay(game, body, author)
		else:
			log.debug("Couldn't get a game for /u/{}".format(author))
			success = False
			response = "Could not load this game. It's possible the game has ended."
	else:
		log.debug("Parsing non-datatable message")
		if isMessage:
			if message.subject.startswith("suggestion"):
				response = processMessageSuggestion(message.body, message.subject)

			elif str(message.author).lower() in wiki.admins:
				if message.subject.startswith("teams"):
					response = processMessageTeams(message.body, message.subject)
				elif body.startswith("newgame"):
					response = processMessageNewGame(message.body, str(message.author))
				elif body.startswith("kick"):
					response = processMessageKickGame(message.body)
				elif body.startswith("pause"):
					response = processMessagePauseGame(message.body)
				elif body.startswith("abandon"):
					response = processMessageAbandonGame(message.body)
				elif body.startswith("status"):
					response = processMessageGameStatus(message.body)
				elif body.startswith("reindex"):
					response = processMessageReindex(message.body)
				elif body.startswith("chew"):
					response = processMessageDefaultChew(message.body)
				elif body.startswith("gamelist"):
					response = processMessageGameList(message.body)
				elif body.startswith("restart"):
					response = processMessageRestartGame(message.body)
				elif body.startswith("rerun"):
					response = processMessageRerunLastPlay(message.body)

	message.mark_read()
	if response is not None:
		if success is not None and not success and dataTable is not None and string_utils.extractTableFromMessage(
				response) is None:
			log.debug("Embedding datatable in reply on failure")
			response = string_utils.embedTableInMessage(response, dataTable)
			if updateWaiting and game is not None:
				if appendMessageId:
					utils.addWaitingId(game, 'return')
				else:
					utils.setWaitingId(game, 'return')
		resultMessage = reddit.replyMessage(message, response)
		if resultMessage is None:
			log.warning("Could not send message")

		elif game is not None and 'return' in game.status.waitingId:
			if appendMessageId:
				utils.clearReturnWaitingId(game)
				utils.addWaitingId(game, resultMessage.fullname)
			else:
				utils.setWaitingId(game, resultMessage.fullname)
			game.dirty = True
			log.debug("Message/comment replied, now waiting on: {}".format(game.status.waitingId))
	else:
		if isMessage:
			log.debug("Couldn't understand message")
			resultMessage = reddit.replyMessage(message,
												"I couldn't understand your message, please try again or message /u/Watchful1 if you need help.")
			if resultMessage is None:
				log.warning("Could not send message")

	if game is not None and game.dirty:
		log.debug("Game is dirty, updating thread")
		utils.updateGameThread(game)

	if game is not None and game.status.waitingAction == Action.END:
		index.endGame(game)
