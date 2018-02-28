import logging.handlers
import re
import praw

import reddit
import utils
import wiki
import globals
import database
import state

log = logging.getLogger("bot")


def processMessageNewGame(body, author):
	log.debug("Processing new game message")

	users = re.findall('(?: /u/)([\w-]*)', body)
	if len(users) == 0:
		log.debug("Could not find an opponent in create game message")
		return "Please resend the message and specify an opponent"
	opponent = users[0]
	log.debug("Found opponent in message /u/{}".format(opponent))

	i, result = utils.verifyCoaches([author, opponent])

	if i == 0 and result == 'team':
		log.debug("Author does not have a team")
		return "It looks like you don't have a team, please contact the /r/FakeCollegeFootball moderators"

	if i == 0 and result == 'game':
		log.debug("Author already has a game")
		return "You're already playing a game, you can't challenge anyone else until that game finishes"

	if result == 'duplicate':
		log.debug("{} challenged themselves to a game".format(author))
		return "You can't challenge yourself to a game"

	if i == 1 and result == 'team':
		log.debug("Opponent does not have a team")
		return "It looks like your opponent doesn't have a team, please contact the /r/FakeCollegeFootball moderators"

	if i == 1 and result == 'game':
		log.debug("Opponent already has a game")
		return "/u/{} is already playing a game".format(opponent)

	authorTeam = wiki.getTeamByCoach(author)
	message = "/u/{}'s {} has challenged you to a game! Reply **accept** or **reject**.".format(author, authorTeam['name'])
	data = {'action': 'newgame', 'opponent': author}
	embeddedMessage = utils.embedTableInMessage(message, data)
	log.debug("Sending message to /u/{} that /u/{} has challenged them to a game".format(opponent, author))
	if reddit.sendMessage(opponent, "Game challenge", embeddedMessage):
		return "I've let /u/{} know that you have challenged them to a game. I'll message you again when they accept".format(opponent)
	else:
		return "Something went wrong, I couldn't find that user"


def processMessageRejectGame(dataTable, author):
	log.debug("Processing reject game message")
	if 'opponent' not in dataTable:
		log.warning("Couldn't find opponent in datatable")
		return False, "I couldn't figure out which opponent you were rejecting. This shouldn't happen, please let /u/Watchful1 know"

	log.debug("Sending message to /u/{} that {} rejected their challenge".format(dataTable['opponent'], author))
	reddit.sendMessage(dataTable['opponent'], "Challenge rejected", "/u/{} has rejected your game challenge".format(author))
	return True, "Challenge successfully rejected"


def processMessageAcceptGame(dataTable, author):
	log.debug("Processing accept game message")
	if 'opponent' not in dataTable:
		log.warning("Couldn't find opponent in datatable")
		return False, "I couldn't figure out which opponent you were accepting. This shouldn't happen, please let /u/Watchful1 know"

	coachNum, result = utils.verifyCoaches([author, dataTable['opponent']])
	if coachNum != -1:
		log.debug("Coaches not verified, {} : {}".format(coachNum, result))
		return False, "Something went wrong, someone is no longer an acceptable coach. Please try to start the game again"

	homeTeam = wiki.getTeamByCoach(dataTable['opponent'].lower())
	awayTeam = wiki.getTeamByCoach(author.lower())
	for team in [homeTeam, awayTeam]:
		team['yardsPassing'] = 0
		team['yardsRushing'] = 0
		team['yardsTotal'] = 0
		team['turnoverInterceptions'] = 0
		team['turnoverFumble'] = 0
		team['fieldGoalsScored'] = 0
		team['fieldGoalsAttempted'] = 0
		team['posTime'] = 0

	game = utils.newGameObject(homeTeam, awayTeam)

	gameThread = utils.getGameThreadText(game)
	gameTitle = "[GAME THREAD] {} @ {}".format(game['away']['name'], game['home']['name'])

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
	message = "The game has started! {}, you're away, call **heads** or **tails** in the air.".format(utils.getCoachString(game, 'away'))
	comment = utils.sendGameComment(game, message, {'action': 'coin'})
	game['waitingId'] = comment.fullname
	log.debug("Comment posted, now waiting on: {}".format(game['waitingId']))
	utils.updateGameThread(game)

	log.debug("Returning game started message")
	return True, "Game started. Find it [here]({}).".format(utils.getLinkToThread(threadID))


def processMessageCoin(game, isHeads, author):
	log.debug("Processing coin toss message: {}".format(str(isHeads)))

	if isHeads == utils.coinToss():
		log.debug("User won coin toss, asking if they want to defer")
		game['waitingAction'] = 'defer'
		game['waitingOn'] = 'home'
		game['waitingId'] = 'return'
		game['dirty'] = True

		message = "{}, {} won the toss, do you want to **receive** or **defer**?".format(utils.getCoachString(game, 'home'), game['home']['name'])
		return True, utils.embedTableInMessage(message, {'action': 'defer'})
	else:
		log.debug("User lost coin toss, asking other team if they want to defer")
		game['waitingAction'] = 'defer'
		game['waitingOn'] = 'away'
		game['waitingId'] = 'return'
		game['dirty'] = True

		message = "{}, {} won the toss, do you want to **receive** or **defer**?".format(utils.getCoachString(game, 'away'), game['away']['name'])
		return True, utils.embedTableInMessage(message, {'action': 'defer'})


def processMessageDefer(game, isDefer, author):
	log.debug("Processing defer message: {}".format(str(isDefer)))

	authorHomeAway = utils.getHomeAwayString(utils.isCoachHome(game, author))
	if isDefer:
		log.debug("User deferred, {} is receiving".format(utils.reverseHomeAway(authorHomeAway)))

		state.setStateTouchback(game, utils.reverseHomeAway(authorHomeAway))
		game['receivingNext'] = authorHomeAway
		game['waitingOn'] = utils.reverseHomeAway(game['waitingOn'])
		game['dirty'] = True
		utils.sendDefensiveNumberMessage(game)

		return True, "{} deferred and will receive the ball in the second half. The game has started!\n\n{}\n\n{}".format(
			game[authorHomeAway]['name'],
		    utils.getCurrentPlayString(game),
		    utils.getWaitingOnString(game))
	else:
		log.debug("User elected to receive, {} is receiving".format(authorHomeAway))

		state.setStateTouchback(game, authorHomeAway)
		game['receivingNext'] = utils.reverseHomeAway(authorHomeAway)
		game['waitingOn'] = utils.reverseHomeAway(game['waitingOn'])
		game['dirty'] = True
		utils.sendDefensiveNumberMessage(game)

		return True, "{} elected to receive. The game has started!\n\n{}\n\n{}".format(
			game[authorHomeAway]['name'],
		    utils.getCurrentPlayString(game),
		    utils.getWaitingOnString(game))


def processMessageDefenseNumber(game, message, author):
	log.debug("Processing defense number message")

	number, resultMessage = utils.extractPlayNumber(message)
	if resultMessage is not None:
		return False, resultMessage

	log.debug("Saving defense number: {}".format(number))
	database.saveDefensiveNumber(game['dataID'], number)

	timeoutMessage = None
	if message.find("timeout") > 0:
		if game['status']['timeouts'][utils.reverseHomeAway(game['status']['possession'])] > 0:
			game['status']['requestedTimeout'][utils.reverseHomeAway(game['status']['possession'])] = 'requested'
			timeoutMessage = "Timeout requested successfully"
		else:
			timeoutMessage = "You requested a timeout, but you don't have any left"

	game['waitingOn'] = utils.reverseHomeAway(game['waitingOn'])
	game['dirty'] = True

	log.debug("Sending offense play comment")
	resultMessage = "{} has submitted their number. {} you're up.\n\n{}\n\n{} reply with {} and your number. [Play list]({})".format(
		game[utils.reverseHomeAway(game['waitingOn'])]['name'],
		game[game['waitingOn']]['name'],
		utils.getCurrentPlayString(game),
		utils.getCoachString(game, game['waitingOn']),
		utils.listSuggestedPlays(game),
		"https://www.reddit.com/r/FakeCollegeFootball/wiki/refbot"
	)
	utils.sendGameComment(game, resultMessage, {'action': 'play'})

	result = ["I've got {} as your number.".format(number)]
	if timeoutMessage is not None:
		result.append(timeoutMessage)
	return True, '\n\n'.join(result)


def processMessageOffensePlay(game, message, author):
	log.debug("Processing offense number message")

	number, numberMessage = utils.extractPlayNumber(message)

	timeoutMessageOffense = None
	timeoutMessageDefense = None
	if message.find("timeout") > 0:
		if game['status']['timeouts'][game['status']['possession']] > 0:
			game['status']['requestedTimeout'][game['status']['possession']] = 'requested'
		else:
			timeoutMessageOffense = "The offense requested a timeout, but they don't have any left"

	playOptions = ['run', 'pass', 'punt', 'field goal', 'kneel', 'spike', 'two point', 'pat']
	playSelected = utils.findKeywordInMessage(playOptions, message)
	play = "default"
	if playSelected == "run":
		play = "run"
	elif playSelected == "pass":
		play = "pass"
	elif playSelected == "punt":
		play = "punt"
	elif playSelected == "field goal":
		play = "fieldGoal"
	elif playSelected == "kneel":
		play = "kneel"
	elif playSelected == "spike":
		play = "spike"
	elif playSelected == "two point":
		play = "twoPoint"
	elif playSelected == "pat":
		play = "pat"
	elif playSelected == "mult":
		return False, "I found multiple plays in your message. Please repost it with just the play and number."
	else:
		return False, "I couldn't find a play in your message"

	success, resultMessage = state.executePlay(game, play, number, numberMessage)

	if game['status']['requestedTimeout'][game['status']['possession']] == 'used':
		timeoutMessageOffense = "The offense is charged a timeout"
	elif game['status']['requestedTimeout'][game['status']['possession']] == 'requested':
		timeoutMessageOffense = "The offense requested a timeout, but it was not used"
	game['status']['requestedTimeout'][game['status']['possession']] = 'none'

	if game['status']['requestedTimeout'][utils.reverseHomeAway(game['status']['possession'])] == 'used':
		timeoutMessageDefense = "The defense is charged a timeout"
	elif game['status']['requestedTimeout'][utils.reverseHomeAway(game['status']['possession'])] == 'requested':
		timeoutMessageDefense = "The defense requested a timeout, but it was not used"
	game['status']['requestedTimeout'][utils.reverseHomeAway(game['status']['possession'])] = 'none'

	result = [resultMessage]
	if timeoutMessageOffense is not None:
		result.append(timeoutMessageOffense)
	if timeoutMessageDefense is not None:
		result.append(timeoutMessageDefense)

	game['waitingOn'] = utils.reverseHomeAway(game['waitingOn'])
	game['dirty'] = True
	if game['waitingAction'] == 'play':
		utils.sendDefensiveNumberMessage(game)

	return success, utils.embedTableInMessage('\n\n'.join(result), {'action': game['waitingAction']})


def processMessageKickGame(body):
	log.debug("Processing kick game message")
	numbers = re.findall('(\d+)', body)
	if len(numbers) < 1:
		log.debug("Couldn't find a game id in message")
		return "Couldn't find a game id in message"
	log.debug("Found number: {}".format(str(numbers[0])))
	success = database.clearGameErrored(numbers[0])
	if success:
		log.debug("Kicked game")
		return "Game {} kicked".format(str(numbers[0]))
	else:
		log.debug("Couldn't kick game")
		return "Couldn't kick game {}".format(str(numbers[0]))


def processMessage(message):
	if isinstance(message, praw.models.Message):
		isMessage = True
		log.debug("Processing a message from /u/{} : {}".format(str(message.author), message.id))
	else:
		isMessage = False
		log.debug("Processing a comment from /u/{} : {}".format(str(message.author), message.id))

	response = None
	success = None
	dataTable = None

	if message.parent_id is not None and (message.parent_id.startswith("t1") or message.parent_id.startswith("t4")):
		if isMessage:
			parent = reddit.getMessage(message.parent_id[3:])
		else:
			parent = reddit.getComment(message.parent_id[3:])

		if parent is not None and str(parent.author).lower() == globals.ACCOUNT_NAME:
			dataTable = utils.extractTableFromMessage(parent.body)
			if dataTable is not None:
				if 'action' not in dataTable:
					dataTable = None
				else:
					dataTable['source'] = parent.fullname
					log.debug("Found a valid datatable in parent message: {}".format(str(dataTable)))

	body = message.body.lower()
	author = str(message.author)
	game = None
	if dataTable is not None:
		if dataTable['action'] == 'newgame' and isMessage:
			keywords = ['accept', 'reject']
			keyword = utils.findKeywordInMessage(keywords, body)
			if keyword == "accept":
				success, response = processMessageAcceptGame(dataTable, str(message.author))
			elif keyword == "reject":
				success, response = processMessageRejectGame(dataTable, str(message.author))
			elif keyword == 'mult':
				success = False
				response = "I found both {} in your message. Please reply with just one of them.".format(' and '.join(keywords))

		else:
			game = utils.getGameByUser(author)
			if game is not None:
				utils.setLogGameID(game['thread'], game['dataID'])
				if game['errored']:
					log.debug("Game is errored, skipping")
					response = "This game is currently in an error state, /u/{} has been contacted to take a look".format(globals.OWNER)
					success = False

				else:
					waitingOn = utils.isGameWaitingOn(game, author, dataTable['action'], dataTable['source'])
					if waitingOn is not None:
						response = waitingOn
						success = False

					elif dataTable['action'] == 'coin' and not isMessage:
						keywords = ['heads', 'tails']
						keyword = utils.findKeywordInMessage(keywords, body)
						if keyword == "heads":
							success, response = processMessageCoin(game, True, str(message.author))
						elif keyword == "tails":
							success, response = processMessageCoin(game, False, str(message.author))
						elif keyword == 'mult':
							success = False
							response = "I found both {} in your message. Please reply with just one of them.".format(' and '.join(keywords))

					elif dataTable['action'] == 'defer' and not isMessage:
						keywords = ['defer', 'receive']
						keyword = utils.findKeywordInMessage(keywords, body)
						if keyword == "defer":
							success, response = processMessageDefer(game, True, str(message.author))
						elif keyword == "receive":
							success, response = processMessageDefer(game, False, str(message.author))
						elif keyword == 'mult':
							success = False
							response = "I found both {} in your message. Please reply with just one of them.".format(' and '.join(keywords))

					elif dataTable['action'] == 'play' and isMessage:
						success, response = processMessageDefenseNumber(game, body, str(message.author))

					elif dataTable['action'] == 'play' and not isMessage:
						success, response = processMessageOffensePlay(game, body, str(message.author))
			else:
				log.debug("Couldn't get a game for /u/{}".format(author))
	else:
		log.debug("Parsing non-datatable message")
		if "newgame" in body and isMessage:
			response = processMessageNewGame(body, str(message.author))
		if "kick" in body and isMessage and str(message.author).lower() == globals.OWNER:
			response = processMessageKickGame(body)

	message.mark_read()
	if response is not None:
		if success is not None and not success and dataTable is not None and utils.extractTableFromMessage(response) is None:
			response = utils.embedTableInMessage(message, dataTable)
			if game is not None:
				game['waitingId'] = 'return'
		resultMessage = reddit.replyMessage(message, response)
		if game is not None and game['waitingId'] == 'return':
			game['waitingId'] = resultMessage.fullname
			log.debug("Message/comment replied, now waiting on: {}".format(game['waitingId']))
	else:
		if isMessage:
			log.debug("Couldn't understand message")
			reddit.replyMessage(message,
			                    "I couldn't understand your message, please try again or message /u/Watchful1 if you need help.")

	if game is not None and game['dirty']:
		utils.updateGameThread(game)
