import os

import utils


def addWinnerFieldToGames():
	folder = "games"
	for fileName in os.listdir(folder):
		if not os.path.isfile(os.path.join(folder, fileName)):
			continue
		game = utils.loadGameObject(fileName)
		game.status.winner = None
		for status in game.previousStatus:
			status.winner = None
		utils.saveGameObject(game)
