import logging.handlers
import re
import praw

import reddit
import utils
import wiki
import globals
import state
import classes
import index
from classes import Play
from classes import Action
from classes import TimeoutOption
from classes import TimeOption

log = logging.getLogger("bot")


def processMessageNewGame(body, author):
	log.debug("Processing new game message")
	teams = re.findall('(\w+)', body)
	if len(teams) < 3:
		log.debug("Could not find an two teams in create game message")
		return "Please resend the message and specify two teams"

	homeTeam = teams[1]
	awayTeam = teams[2]
	log.debug("Found teams in message {} vs {}".format(homeTeam, awayTeam))

	i, result = utils.verifyTeams([homeTeam, awayTeam])

	if result == 'duplicate':
		log.debug("Teams are the same")
		return "You can't have a team play itself"

	if i == 0 and result == 'team':
		log.debug("Home is not a valid team")
		return "The home team is not valid"

	if i == 1 and result == 'team':
		log.debug("Away is not a valid team")
		return "The away team is not valid"

	startTime = None
	location = None
	station = None
	homeRecord = None
	awayRecord = None

	for match in re.finditer('(?: )(\w+)(?:=")([^"]*)', body):
		if match.group(1) == "start":
			startTime = utils.escapeMarkdown(match.group(2))
			log.debug("Found start time: {}".format(startTime))
		elif match.group(1) == "location":
			location = utils.escapeMarkdown(match.group(2))
			log.debug("Found location: {}".format(location))
		elif match.group(1) == "station":
			station = utils.escapeMarkdown(match.group(2))
			log.debug("Found station: {}".format(station))
		elif match.group(1) == "homeRecord":
			homeRecord = utils.escapeMarkdown(match.group(2))
			log.debug("Found home record: {}".format(homeRecord))
		elif match.group(1) == "awayRecord":
			awayRecord = utils.escapeMarkdown(match.group(2))
			log.debug("Found away record: {}".format(awayRecord))

	return utils.startGame(homeTeam, awayTeam, startTime, location, station, homeRecord, awayRecord)


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
			questionString = "do you want to **defend** or **attack**?"
		else:
			questionString = "do you want to **receive** or **defer**?"
		message = "{}, {} won the toss, {}".format(utils.getCoachString(game, False), game.away.name, questionString)
		return True, utils.embedTableInMessage(message, utils.getActionTable(game, Action.DEFER))
	else:
		log.debug("User lost coin toss, asking other team if they want to defer")
		game.status.waitingAction = Action.DEFER
		game.status.waitingOn.set(True)
		utils.setWaitingId(game, 'return')
		game.dirty = True

		if utils.isGameOvertime(game):
			questionString = "do you want to **defend** or **attack**?"
		else:
			questionString = "do you want to **receive** or **defer**?"
		message = "{}, {} won the toss, {}".format(utils.getCoachString(game, True), game.home.name, questionString)
		return True, utils.embedTableInMessage(message, utils.getActionTable(game, Action.DEFER))


def processMessageDefer(game, isDefer, author):
	log.debug("Processing defer message: {}".format(str(isDefer)))

	authorHomeAway = utils.coachHomeAway(game, author)
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
				utils.getCurrentPlayString(game),
				utils.getWaitingOnString(game))
		else:
			log.debug("User elected to attack, {} is attacking".format(authorHomeAway))

			state.setStateOvertimeDrive(game, authorHomeAway)
			game.status.receivingNext = authorHomeAway.negate()
			game.status.waitingOn.reverse()
			game.dirty = True
			utils.sendDefensiveNumberMessage(game)

			return True, "{} elected to attack. Overtime has started!\n\n{}\n\n{}".format(
				game.team(authorHomeAway).name,
				utils.getCurrentPlayString(game),
				utils.getWaitingOnString(game))
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
				utils.getCurrentPlayString(game),
				utils.getWaitingOnString(game))
		else:
			log.debug("User elected to receive, {} is receiving".format(authorHomeAway))

			state.setStateKickoff(game, authorHomeAway.negate())
			game.status.receivingNext = authorHomeAway.negate()
			game.status.waitingOn.reverse()
			game.dirty = True
			utils.sendDefensiveNumberMessage(game)

			return True, "{} elected to receive. The game has started!\n\n{}\n\n{}".format(
				game.team(authorHomeAway).name,
				utils.getCurrentPlayString(game),
				utils.getWaitingOnString(game))


def processMessageDefenseNumber(game, message, author):
	log.debug("Processing defense number message")

	number, resultMessage = utils.extractPlayNumber(message)
	if resultMessage is not None:
		return False, resultMessage

	log.debug("Saving defense number: {}".format(number))
	game.status.defensiveNumber = number

	timeoutMessage = None
	if "timeout" in message:
		if game.status.state(game.status.possession.negate()).timeouts > 0:
			game.status.state(game.status.possession.negate()).requestedTimeout = TimeoutOption.REQUESTED
			timeoutMessage = "Timeout requested successfully"
		else:
			timeoutMessage = "You requested a timeout, but you don't have any left"

	game.status.waitingOn.reverse()
	game.dirty = True
	utils.setGamePlayed(game)

	log.debug("Sending offense play comment")
	resultMessage = "{} has submitted their number. {} you're up. You have until {}.\n\n{}\n\n{} reply with {} and your number. [Play list]({}){}".format(
		game.team(game.status.waitingOn.negate()).name,
		game.team(game.status.waitingOn).name,
		utils.renderDatetime(game.playclock),
		utils.getCurrentPlayString(game),
		utils.getCoachString(game, game.status.waitingOn),
		utils.listSuggestedPlays(game),
		"https://www.reddit.com/r/FakeCollegeFootball/wiki/refbot",
		"\n\nThe clock has stopped" if not game.status.timeRunoff else ""
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
	if "timeout" in message:
		if game.status.state(game.status.possession).timeouts > 0:
			game.status.state(game.status.possession).requestedTimeout = TimeoutOption.REQUESTED
		else:
			timeoutMessageOffense = "The offense requested a timeout, but they don't have any left"

	if game.forceChew:
		timeOption = TimeOption.CHEW
	else:
		timeOption = TimeOption.NORMAL
	if any(x in message for x in ['chew the clock', 'milk the clock', 'chew clock']):
		timeOption = TimeOption.CHEW
	elif any(x in message for x in ['hurry up', 'no huddle', 'no-huddle']):
		timeOption = TimeOption.HURRY
	elif any(x in message for x in ['normal']):
		timeOption = TimeOption.NORMAL

	normalOptions = ["run", "pass", "punt", "field goal", "kneel", "spike"]
	conversionOptions = ["two point", "pat"]
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
		play = Play.PAT
	elif playSelected == "normal":
		play = Play.KICKOFF_NORMAL
	elif playSelected == "squib":
		play = Play.KICKOFF_SQUIB
	elif playSelected == "onside":
		play = Play.KICKOFF_ONSIDE
	elif playSelected == "mult":
		log.debug("Found multiple plays")
		return False, "I found multiple plays in your message. Please repost it with just the play and number."
	else:
		log.debug("Didn't find any plays")
		return False, "I couldn't find a play in your message"

	number, numberMessage = utils.extractPlayNumber(message)
	if play not in classes.timePlays and number == -1:
		log.debug("Trying to execute a {} play, but didn't have a number".format(play))
		return False, numberMessage

	success, resultMessage = state.executePlay(game, play, number, timeOption)

	if game.status.state(game.status.possession).requestedTimeout == TimeoutOption.USED:
		timeoutMessageOffense = "The offense is charged a timeout"
	elif game.status.state(game.status.possession).requestedTimeout == TimeoutOption.REQUESTED:
		timeoutMessageOffense = "The offense requested a timeout, but it was not used"
	game.status.state(game.status.possession).requestedTimeout = TimeoutOption.NONE

	if game.status.state(game.status.possession.negate()).requestedTimeout == TimeoutOption.USED:
		timeoutMessageDefense = "The defense is charged a timeout"
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
	game.dirty = True
	utils.setGamePlayed(game)
	if game.status.waitingAction in classes.playActions:
		utils.sendDefensiveNumberMessage(game)
	elif game.status.waitingAction == Action.OVERTIME:
		log.debug("Starting overtime, posting coin toss comment")
		message = "Overtime has started! {}, you're away, call **heads** or **tails** in the air.".format(
			utils.getCoachString(game, False))
		comment = utils.sendGameComment(game, message, utils.getActionTable(game, Action.COIN))
		utils.setWaitingId(game, comment.fullname)
		game.status.waitingAction = Action.COIN
		game.status.waitingOn = classes.HomeAway(False)

	return success, utils.embedTableInMessage('\n\n'.join(result), utils.getActionTable(game, game.status.waitingAction))


def processMessageKickGame(body):
	log.debug("Processing kick game message")
	threadIds = re.findall('([\da-z]{6})', body)
	if len(threadIds) < 1:
		log.debug("Couldn't find a thread id in message")
		return "Couldn't find a thread id in message"
	log.debug("Found thread id: {}".format(threadIds[0]))

	game = utils.loadGameObject(threadIds[0])
	if game is None:
		return "Game not found: {}".format(threadIds[0])

	game = index.reloadAndReturn(threadIds[0])
	index.clearGameErrored(game)
	utils.saveGameObject(game)
	result = ["Kicked game: {}".format(threadIds[0])]

	statusIndex = re.findall('(?:revert:)(\d+)', body)
	if len(statusIndex) > 0:
		log.debug("Reverting to status: {}".format(statusIndex[0]))
		utils.revertStatus(game, int(statusIndex[0]))
		utils.saveGameObject(game)
		result.append("Reverted to status: {}".format(statusIndex[0]))

	messageFullname = re.findall('(?:message:)(t\d_[\da-z]{6,})', body)
	if len(messageFullname) > 0:
		log.debug("Reprocessing message/comment: {}".format(messageFullname[0]))
		message = reddit.getThingFromFullname(messageFullname[0])
		if message is None:
			return "Something went wrong. Not valid fullname: {}".format(messageFullname[0])
		processMessage(message, True)
		result.append("Reprocessed message: {}".format(messageFullname[0]))

	log.debug("Finished kicking game")
	return '\n\n'.join(result)


def processMessagePauseGame(body):
	log.debug("Processing pause game message")
	threadIds = re.findall('([\da-z]{6})', body)
	if len(threadIds) < 1:
		log.debug("Couldn't find a thread id in message")
		return "Couldn't find a thread id in message"
	log.debug("Found thread id: {}".format(threadIds[0]))

	hours = re.findall('(\d{1,3})', body)
	if len(hours) < 1:
		log.debug("Couldn't find a number of hours in message")
		return "Couldn't find a number of hours in message"
	log.debug("Found hours: {}".format(hours[0]))

	game = index.reloadAndReturn(threadIds[0])
	utils.pauseGame(game, hours[0])
	utils.saveGameObject(game)

	return "Game {} paused for {} hours".format(threadIds[0], hours[0])


def processMessageAbandonGame(body):
	log.debug("Processing abandon game message")
	threadIds = re.findall('(?: )([\da-z]{6})', body)
	if len(threadIds) < 1:
		log.debug("Couldn't find a thread id in message")
		return "Couldn't find a thread id in message"
	log.debug("Found thread id: {}".format(threadIds[0]))

	game = utils.loadGameObject(threadIds[0])
	if game is None:
		return "Game not found: {}".format(threadIds[0])

	utils.endGame(game, "Abandoned", False)
	utils.updateGameThread(game)
	utils.saveGameObject(game)

	return "Game {} abandoned".format(threadIds[0])


def processMessageGameStatus(body):
	log.debug("Processing game status message")
	threadIds = re.findall('(?: )([\da-z]{6})', body)
	if len(threadIds) < 1:
		log.debug("Couldn't find a thread id in message")
		return "Couldn't find a thread id in message"
	log.debug("Found thread id: {}".format(threadIds[0]))

	game = utils.loadGameObject(threadIds[0])
	if game is None:
		return "Game {} doesn't exist".format(threadIds[0])
	else:
		return utils.renderGameStatusMessage(game)


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

	game = utils.loadGameObject(threadIds[0])
	if game is None:
		return "Game not found: {}".format(threadIds[0])

	if "normal" in body:
		game.forceChew = False
		result = "Game changed to normal plays by default: {}".format(threadIds[0])
	else:
		game.forceChew = True
		result = "Game changed to chew the clock plays by default: {}".format(threadIds[0])

	utils.updateGameThread(game)
	utils.saveGameObject(game)

	return result


def processMessage(message, force=False):
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

		if parent is not None and str(parent.author).lower() == globals.ACCOUNT_NAME:
			dataTable = utils.extractTableFromMessage(parent.body)
			if dataTable is not None:
				if 'action' not in dataTable or 'thread' not in dataTable:
					dataTable = None
				else:
					dataTable['source'] = parent.fullname
					log.debug("Found a valid datatable in parent message: {}".format(str(dataTable)))

	body = message.body.lower()
	author = str(message.author)
	game = None
	appendMessageId = False
	if dataTable is not None:
		game = index.reloadAndReturn(dataTable['thread'])
		if game is not None:
			utils.cycleStatus(game, message.fullname)
			utils.setLogGameID(game.thread, game)

			waitingOn = utils.isGameWaitingOn(game, author, dataTable['action'], dataTable['source'], force)
			if waitingOn is not None:
				response = waitingOn
				success = False
				updateWaiting = False

			elif game.errored:
				log.debug("Game is errored, skipping")
				response = "This game is currently in an error state, /u/{} has been contacted to take a look".format(
					globals.OWNER)
				success = False
				updateWaiting = False

			else:
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
						keywords = ["defend", "attack"]
					else:
						keywords = ["defer", "receive"]
					keyword = utils.findKeywordInMessage(keywords, body)
					if keyword == "defer" or keyword == "defend":
						success, response = processMessageDefer(game, True, author)
					elif keyword == "receive" or keyword == "attack":
						success, response = processMessageDefer(game, False, author)
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
	else:
		log.debug("Parsing non-datatable message")
		if isMessage and str(message.author).lower() in wiki.admins:
			if body.startswith("newgame"):
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

	message.mark_read()
	if response is not None:
		if success is not None and not success and dataTable is not None and utils.extractTableFromMessage(
				response) is None:
			log.debug("Embedding datatable in reply on failure")
			response = utils.embedTableInMessage(response, dataTable)
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
