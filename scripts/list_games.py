import discord_logging
import os

log = discord_logging.init_logging(debug=True)

import file_utils


if __name__ == "__main__":
	count_games = 0
	folder = r"C:\Users\greg\Desktop\PyCharm\CFBRef\gamesOld"
	for gameFile in os.listdir(folder):
		game = file_utils.loadGameObject(filename=f"{folder}\\{gameFile}")
		count_games += 1
		if game is not None:
			log.info(f"{game.deadline.strftime('%Y-%m-%d')} : {game.home.name} vs {game.away.name} : {game.playGist}")
	log.info(f"{count_games}")
