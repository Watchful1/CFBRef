import os

import utils
import globals
import classes


def addWinnerFieldToGames():
	folder = globals.SAVE_FOLDER_NAME
	for fileName in os.listdir(folder):
		if not os.path.isfile(os.path.join(folder, fileName)):
			continue
		game = utils.loadGameObject(fileName)
		game.status.winner = None
		for status in game.previousStatus:
			status.winner = None
		utils.saveGameObject(game)


def archiveOutstandingFinishedGames():
	folder = globals.SAVE_FOLDER_NAME
	for fileName in os.listdir(folder):
		if not os.path.isfile(os.path.join(folder, fileName)):
			continue
		game = utils.loadGameObject(fileName)
		if game.status.quarterType == classes.QuarterType.END:
			utils.archiveGameFile(game.thread)
