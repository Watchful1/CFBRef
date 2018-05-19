import os
import logging.handlers
from datetime import datetime
from datetime import timedelta

import globals
import utils
from classes import Action

log = logging.getLogger("bot")

games = {}
errored = set()


def init():
	for gameFile in os.listdir(globals.SAVE_FOLDER_NAME):
		reloadAndReturn(gameFile)


def addNewGame(game):
	games[game.thread] = game


def reloadAndReturn(thread):
	game = utils.loadGameObject(thread)
	if game.status.waitingAction != Action.END:
		games[game.thread] = game
		if game.errored and game.thread not in errored:
			errored.add(game.thread)
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
	errored.add(game.thread)


def clearGameErrored(game):
	errored.remove(game.thread)
	game.errored = False
	game.deadline = game.deadline + (datetime.utcnow() - game.playclock)
	game.playclock = datetime.utcnow() + timedelta(hours=24)
