import logging.handlers
import re
import praw

import reddit
import utils
import wiki
import globals
import database

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
	message = "/u/{}'s {} has challenged you to a game! Reply accept or reject.".format(author, authorTeam['name'])
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

	log.debug("Sending message to home coaches")
	reddit.sendMessage(game['home']['coaches'], "Game started!",
	                   "/u/{} has accepted your challenge and a new game has begun. Find it [here]({}).".format(author, utils.getLinkToThread(threadID)))

	awayMessage = "Game started. Find it [here]({}).\n\nIt's your coin toss, reply with heads or tails.".format(utils.getLinkToThread(threadID))
	return utils.embedTableInMessage(awayMessage, {'action': 'coin'})


def processMessageCoin(isHeads, author):
	log.debug("Processing coin toss message: {}".format(str(isHeads)))
	game = utils.getGameByUser(author)

	if game['waitingAction'] != 'coin':
		log.debug("Not waiting on coin toss: {}".format(game['waitingAction']))
		return "I'm not waiting on a coin toss for this game, are you sure you replied to the right message?"

	if (game['waitingOn'] == 'home') != utils.isCoachHome(game, author):
		log.debug("Not waiting on message author's team")
		return "I'm not waiting on a message from you, are you sure you responded to the right message?"

	if isHeads == utils.coinToss():
		log.debug("User won coin toss, asking if they want to defer")
		game['waitingAction'] = 'defer'
		utils.updateGameThread(game)
		message = "You won the toss, reply receive or defer"
		return utils.embedTableInMessage(message, {'action': 'defer'})
	else:
		log.debug("User lost coin toss, asking other team if they want to defer")
		game['waitingAction'] = 'defer'
		game['waitingOn'] = 'home'
		utils.updateGameThread(game)

		utils.sendGameMessage(True, game, "You have won the toss, reply receive or defer", {'action': 'defer'})
		return "You have lost the toss, asking the other team if they want to receive or defer"


def processMessageDefer(isDefer, author):
	log.debug("Processing defer toss message: {}".format(str(isDefer)))
	game = utils.getGameByUser(author)

	if game['waitingAction'] != 'defer':
		log.debug("Not waiting on defer: {}".format(game['waitingAction']))
		return "I'm not waiting on a receive/defer, are you sure you replied to the right message?"

	if (game['waitingOn'] == 'home') != utils.isCoachHome(game, author):
		log.debug("Not waiting on message author's team")
		return "I'm not waiting on a message from you, are you sure you responded to the right message?"

	if isDefer:






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
			body = message.body.lower()
			if dataTable is not None:
				if dataTable['action'] == 'newgame':
					if body.startswith("accept"):
						response = processMessageAcceptGame(dataTable, str(message.author))
					elif body.startswith("reject"):
						response = processMessageRejectGame(dataTable, str(message.author))
				if dataTable['action'] == 'coin':
					if body.startswith("heads"):
						response = processMessageCoin(True, str(message.author))
					elif body.startswith("tails"):
						response = processMessageCoin(False, str(message.author))
				if dataTable['action'] == 'defer':
					if body.startswith("defer"):
						response = processMessageDefer(True, str(message.author))
					elif body.startswith("receive"):
						response = processMessageDefer(False, str(message.author))


			if body.startswith("newgame"):
				response = processMessageNewGame(body, str(message.author))

			message.mark_read()
			if response is not None:
				message.reply(response)
			else:
				log.debug("Couldn't understand message")
				message.reply("I couldn't understand your message, please try again or message /u/Watchful1 if you need help.")
