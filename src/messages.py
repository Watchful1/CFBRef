import logging.handlers
import re
import praw

import reddit
import utils
import wiki
import globals
import database
import state
from globals import actions

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
		return "I couldn't figure out which opponent you were rejecting. This shouldn't happen, please let /u/Watchful1 know"

	log.debug("Sending message to /u/{} that {} rejected their challenge".format(dataTable['opponent'], author))
	reddit.sendMessage(dataTable['opponent'], "Challenge rejected", "/u/{} has rejected your game challenge".format(author))
	return "Challenge successfully rejected"


def processMessageAcceptGame(dataTable, author):
	log.debug("Processing accept game message")
	if 'opponent' not in dataTable:
		log.warning("Couldn't find opponent in datatable")
		return "I couldn't figure out which opponent you were accepting. This shouldn't happen, please let /u/Watchful1 know"

	coachNum, result = utils.verifyCoaches([author, dataTable['opponent']])
	if coachNum != -1:
		log.debug("Coaches not verified, {} : {}".format(coachNum, result))
		return "Something went wrong, someone is no longer an acceptable coach. Please try to start the game again"

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
	gameTitle = "[GAME THREAD] {} vs {}".format(game['home']['name'], game['away']['name'])

	threadID = str(reddit.submitSelfPost(globals.SUBREDDIT, gameTitle, gameThread))
	log.debug("Game thread created: {}".format(threadID))

	gameID = database.createNewGame(threadID)
	log.debug("Game database record created: {}".format(gameID))

	for user in game['home']['coaches']:
		database.addCoach(gameID, user, True)
		log.debug("Coach added to home: {}".format(user))
	for user in game['away']['coaches']:
		database.addCoach(gameID, user, False)
		log.debug("Coach added to away: {}".format(user))

	log.debug("Game started, posting coin toss comment")
	message = "The game has started! {}, you're home, call **heads** or **tails** in the air.".format(utils.getCoachString(game, 'home'))
	utils.sendGameComment(game, message, {'action': 'coin'})

	log.debug("Returning game started message")
	return "Game started. Find it [here]({}).".format(utils.getLinkToThread(threadID))


def processMessageCoin(isHeads, author):
	log.debug("Processing coin toss message: {}".format(str(isHeads)))
	game = utils.getGameByUser(author)

	waitingOn = utils.isGameWaitingOn(game, author, actions.coin)
	if waitingOn is not None:
		return waitingOn

	if isHeads == utils.coinToss():
		log.debug("User won coin toss, asking if they want to defer")
		game['waitingAction'] = actions.defer
		utils.updateGameThread(game)

		message = "{} won the toss, do you want to **receive** or **defer**?".format(game['home']['name'])
		return utils.embedTableInMessage(message, {'action': 'defer'})
	else:
		log.debug("User lost coin toss, asking other team if they want to defer")
		game['waitingAction'] = actions.defer
		game['waitingOn'] = 'away'
		utils.updateGameThread(game)

		message = "{}, {} won the toss, do you want to **receive** or **defer**?".format(utils.getCoachString(game, 'away'), game['away']['name'])
		return utils.embedTableInMessage(message, {'action': 'defer'})


def processMessageDefer(isDefer, author):
	log.debug("Processing defer message: {}".format(str(isDefer)))
	game = utils.getGameByUser(author)

	waitingOn = utils.isGameWaitingOn(game, author, actions.defer)
	if waitingOn is not None:
		return waitingOn

	authorHomeAway = utils.getHomeAwayString(utils.isCoachHome(game, author))
	if isDefer:
		log.debug("User deferred, {} is receiving".format(utils.reverseHomeAway(authorHomeAway)))

		state.setStateTouchback(game, utils.reverseHomeAway(authorHomeAway))
		utils.updateGameThread(game)
		utils.sendDefensiveNumberMessage(game)

		return "{} deferred and will receive the ball in the second half. The game has started!\n\n{}\n\n{}".format(
			game[authorHomeAway]['name'],
		    utils.getCurrentPlayString(game),
		    utils.getWaitingOnString(game))
	else:
		log.debug("User elected to receive, {} is receiving".format(authorHomeAway))

		state.setStateTouchback(game, authorHomeAway)
		utils.updateGameThread(game)
		utils.sendDefensiveNumberMessage(game)

		return "{} elected to receive. The game has started!\n\n{}\n\n{}".format(
			game[authorHomeAway]['name'],
		    utils.getCurrentPlayString(game),
		    utils.getWaitingOnString(game))


def processMessageDefenseNumber(message, author):
	log.debug("Processing defense number message")
	game = utils.getGameByUser(author)

	waitingOn = utils.isGameWaitingOn(game, author, actions.play)
	if waitingOn is not None:
		return waitingOn

	number, resultMessage = utils.extractPlayNumber(message)
	if resultMessage is not None:
		return resultMessage

	log.debug("Saving defense number: {}".format(number))
	database.saveDefensiveNumber(game['dataID'], number)

	game['waitingOn'] = utils.reverseHomeAway(game['waitingOn'])
	utils.updateGameThread(game)

	log.debug("Sending offense play comment")
	message = "{} has submitted their number, {} you're up.\n\n{}\n\n{} reply with run or pass and your number.".format(
		game[utils.reverseHomeAway(game['waitingOn'])]['name'],
		game[game['waitingOn']]['name'],
		utils.getCurrentPlayString(game),
		utils.getCoachString(game, game['waitingOn']))
	utils.sendGameComment(game, message, {'action': 'play'})

	return "I've got {} as your number.".format(number)


def processMessageOffensePlay(message, author):
	log.debug("Processing offense number message")
	game = utils.getGameByUser(author)

	waitingOn = utils.isGameWaitingOn(game, author, actions.play)
	if waitingOn is not None:
		return waitingOn

	number, numberMessage = utils.extractPlayNumber(message)

	if message.find("timeout"):
		timeout = True
	else:
		timeout = False

	if message.startsWith("run"):
		play = "run"
	elif message.startsWith("pass"):
		play = "pass"
	elif message.startsWith("punt"):
		play = "punt"
	elif message.startsWith("field goal"):
		play = "fieldGoal"
	elif message.startsWith("kneel"):
		play = "kneel"
	elif message.startsWith("spike"):
		play = "spike"
	elif message.startsWith("two point"):
		play = "twoPoint"
	elif message.startsWith("pat"):
		play = "pat"
	else:
		return "I couldn't find a play in your message"

	resultMessage = state.executePlay(game, play, number, numberMessage, timeout)


def processMessages():
	for message in reddit.getMessages():
		log.debug("Processing a message from /u/{}".format(str(message.author)))

		response = None
		dataTable = None

		if message.parent_id is not None:
			parent = reddit.getMessage(message.parent_id[3:])
			if str(parent.author).lower() == globals.ACCOUNT_NAME:
				dataTable = utils.extractTableFromMessage(parent.body)
				if 'action' not in dataTable:
					dataTable = None
				else:
					log.debug("Found a valid datatable in parent message")

		if isinstance(message, praw.models.Message):
			isMessage = True
		else:
			isMessage = False

		body = message.body.lower()
		if dataTable is not None:
			if dataTable['action'] == actions.newGame and isMessage:
				if body.startswith("accept"):
					response = processMessageAcceptGame(dataTable, str(message.author))
				elif body.startswith("reject"):
					response = processMessageRejectGame(dataTable, str(message.author))

			if dataTable['action'] == actions.coin and not isMessage:
				if body.startswith("heads"):
					response = processMessageCoin(True, str(message.author))
				elif body.startswith("tails"):
					response = processMessageCoin(False, str(message.author))

			if dataTable['action'] == actions.defer and not isMessage:
				if body.startswith("defer"):
					response = processMessageDefer(True, str(message.author))
				elif body.startswith("receive"):
					response = processMessageDefer(False, str(message.author))

			if dataTable['action'] == actions.play and isMessage:
				response = processMessageDefenseNumber(body, str(message.author))

			if dataTable['action'] == actions.play and not isMessage:
				response = processMessageOffensePlay(body, str(message.author))

			if body.startswith("newgame") and isMessage:
				response = processMessageNewGame(body, str(message.author))

			message.mark_read()
			if response is not None:
				message.reply(response)
			else:
				if isMessage:
					log.debug("Couldn't understand message")
					message.reply("I couldn't understand your message, please try again or message /u/Watchful1 if you need help.")
