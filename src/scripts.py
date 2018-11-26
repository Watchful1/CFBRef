import os
import sys
import logging
import file_utils
import globals
import classes

import wiki

### Logging setup ###
LOG_LEVEL = logging.DEBUG
if not os.path.exists(globals.LOG_FOLDER_NAME):
	os.makedirs(globals.LOG_FOLDER_NAME)
LOG_FILENAME = globals.LOG_FOLDER_NAME+"/"+"bot.log"
LOG_FILE_BACKUPCOUNT = 5
LOG_FILE_MAXSIZE = 1024 * 256 * 64

class ContextFilter(logging.Filter):
	def filter(self, record):
		record.gameid = globals.logGameId
		return True

log = logging.getLogger("bot")
log.setLevel(LOG_LEVEL)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s:%(gameid)s %(message)s')
log_stdHandler = logging.StreamHandler()
log_stdHandler.setFormatter(log_formatter)
log.addHandler(log_stdHandler)
log.addFilter(ContextFilter())
if LOG_FILENAME is not None:
	log_fileHandler = logging.handlers.RotatingFileHandler(LOG_FILENAME, maxBytes=LOG_FILE_MAXSIZE, backupCount=LOG_FILE_BACKUPCOUNT)
	log_fileHandler.setFormatter(log_formatter)
	log.addHandler(log_fileHandler)


def addWinnerFieldToGames():
	folder = globals.SAVE_FOLDER_NAME
	for fileName in os.listdir(folder):
		if not os.path.isfile(os.path.join(folder, fileName)):
			continue
		game = file_utils.loadGameObject(fileName)
		game.status.winner = None
		for status in game.previousStatus:
			status.winner = None
			file_utils.saveGameObject(game)


def archiveOutstandingFinishedGames():
	folder = globals.SAVE_FOLDER_NAME
	for fileName in os.listdir(folder):
		if not os.path.isfile(os.path.join(folder, fileName)):
			continue
		game = file_utils.loadGameObject(fileName)
		if game.status.quarterType == classes.QuarterType.END:
			file_utils.archiveGameFile(game.thread)


def testPlaysTimes():
	wiki.loadPlays()
	log.info(f"Loaded plays: {len(wiki.plays)}")
	wiki.loadTimes()
	log.info(f"Loaded times: {len(wiki.times)}")


if len(sys.argv) < 2:
	print("No arguments")
	sys.exit(0)

functionName = sys.argv[1]
if functionName == "testPlaysTimes":
	testPlaysTimes()
