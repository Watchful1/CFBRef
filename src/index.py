import os
import logging.handlers
import traceback
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
		if game is not None:
			changed = False
			for team in [game.home, game.away]:
				wikiTeam = wiki.getTeamByTag(team.tag)
				if ((team.coaches > wikiTeam.coaches) - (team.coaches < wikiTeam.coaches)) != 0:
					log.debug("Coaches for game {}, team {} changed from {} to {}".format(
						game.thread,
						team.tag,
						team.coaches,
						wikiTeam.coaches
					))
					changed = True
					team.coaches = wikiTeam.coaches

			if changed:
				try:
					log.debug("Reverting status and reprocessing {}".format(game.previousStatus[0].messageId))
					utils.revertStatus(game, 0)
					utils.saveGameObject(game)
					message = reddit.getThingFromFullname(game.status.messageId)
					if message is None:
						return "Something went wrong. Not valid fullname: {}".format(game.status.messageId)
					messages.processMessage(message, True)
				except Exception as err:
					log.warning(traceback.format_exc())
					log.warning("Unable to revert game when changing coaches")

			games[game.thread] = game


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
	for thread in games:
		game = games[thread]
		if not game.errored and game.playclock < datetime.utcnow():
			pastPlayclock.append(game)
	return pastPlayclock


def getGamesPastPlayclockWarning():
	pastPlayclock = []
	for thread in games:
		game = games[thread]
		if not game.errored and not game.playclockWarning and game.playclock - timedelta(hours=12) < datetime.utcnow():
			pastPlayclock.append(game)
	return pastPlayclock


def endGame(game):
	if game.thread in games:
		del games[game.thread]


def setGameErrored(game):
	game.errored = True
	game.playclock = datetime.utcnow()


def clearGameErrored(game):
	game.errored = False
	game.deadline = game.deadline + (datetime.utcnow() - game.playclock)
	game.playclock = datetime.utcnow() + timedelta(hours=24)
