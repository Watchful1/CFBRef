#!/usr/bin/python3

import os
import logging.handlers
import time
import sys
import signal
import traceback

import globals
import reddit
import messages
import database
import wiki
import utils

### Logging setup ###
LOG_LEVEL = logging.DEBUG
if not os.path.exists(globals.LOG_FOLDER_NAME):
	os.makedirs(globals.LOG_FOLDER_NAME)
LOG_FILENAME = globals.LOG_FOLDER_NAME+"/"+"bot.log"
LOG_FILE_BACKUPCOUNT = 5
LOG_FILE_MAXSIZE = 1024 * 256 * 16


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


def signal_handler(signal, frame):
	log.info("Handling interupt")
	database.close()
	sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


log.debug("Connecting to reddit")

once = False
debug = False
user = None
if len(sys.argv) >= 2:
	user = sys.argv[1]
	for arg in sys.argv:
		if arg == 'once':
			once = True
		elif arg == 'debug':
			debug = True
else:
	log.error("No user specified, aborting")
	sys.exit(0)


if not reddit.init(user):
	sys.exit(0)

database.init()

wiki.loadPages()

for message in reddit.getMessageStream():
	startTime = time.perf_counter()
	log.debug("Processing message")
	wiki.loadPages()

	try:
		messages.processMessage(message)
	except Exception as err:
		log.warning("Error in main loop")
		log.warning(traceback.format_exc())
		if globals.gameId is not None:
			log.debug("Setting game {} as errored".format(globals.gameId))
			database.setGameErrored(globals.gameId)
			ownerMessage = "[Game]({}) errored. Click [here]({}) to clear."\
				.format("{}/{}".format(globals.SUBREDDIT_LINK, globals.logGameId[1:-1]),
			            utils.buildMessageLink(
                            globals.ACCOUNT_NAME,
                            "Kick game",
                            "kick {}".format(globals.gameId)
                        ))
		else:
			ownerMessage = "Unable to process message from /u/{}, skipping".format(str(message.author))

		try:
			reddit.sendMessage(globals.OWNER, "NCFAA game errored", ownerMessage)
			message.mark_read()
		except Exception as err2:
			log.warning("Error sending error message")
			log.warning(traceback.format_exc())

	log.debug("Message processed after: %d", int(time.perf_counter() - startTime))
	utils.clearLogGameID()
	if once:
		database.close()
		break
