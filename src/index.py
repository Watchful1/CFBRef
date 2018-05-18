import os
import logging.handlers
from datetime import datetime

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
		if game.errored:
			errored.add(game.threadid)
		return game
	else:
		return None


def getGamesPastPlayclock():
	pastPlayclock = []
	for game in games:
		if game.playclock < datetime.utcnow():
			pastPlayclock.append(game)


def endGame(game):
	games.pop(game.thread)


def setGameErrored(game):
	errored.add(game.thread)
	sdfsdf #fix game timers here


def clearGameErrored(thread):
	errored.remove(thread)


def getGameErrored(thread):
	return thread in errored
