import os
import logging.handlers
from datetime import datetime
from datetime import timedelta

import globals
import utils
import wiki
import reddit
import messages
from classes import Action

log = logging.getLogger("bot")

games = {}


def init():
	global games
	games = {}
	for gameFile in os.listdir(globals.SAVE_FOLDER_NAME):
		game = reloadAndReturn(gameFile)
		changed = False
		for team in [game.home, game.away]:
			wikiTeam = wiki.getTeamByTag(team.tag)
			if ((team.coaches > wikiTeam.coaches) - (team.coachs < wikiTeam.coaches)) != 0:
				log.debug("Coaches for game {}, team {} changed from [{}] to [{}]".format(
					game.thread,
					team.tag,
					team.coaches,
					wikiTeam.coaches
				))
				changed = True
				team.coaches = wikiTeam.coaches

		if changed:
			log.debug("Reverting status and reprocessing {}".format(game.previousStatus[0].messageId))
			utils.revertStatus(game, 0)
			message = reddit.getThingFromFullname(game.status.messageId)
			if message is None:
				return "Something went wrong. Not valid fullname: {}".format(game.status.messageId)
			messages.processMessage(message)
			utils.saveGameObject(game)


def addNewGame(game):
	games[game.thread] = game


def reloadAndReturn(thread):
	game = utils.loadGameObject(thread)
	if game.status.waitingAction != Action.END:
		games[game.thread] = game
		return game
	else:
		return None


def getGamesPastPlayclock():
	pastPlayclock = []
	for game in games:
		if not game.errored and game.playclock < datetime.utcnow():
			pastPlayclock.append(game)


def endGame(game):
	games.pop(game.thread)


def setGameErrored(game):
	game.playclock = datetime.utcnow()


def clearGameErrored(game):
	game.errored = False
	game.deadline = game.deadline + (datetime.utcnow() - game.playclock)
	game.playclock = datetime.utcnow() + timedelta(hours=24)
