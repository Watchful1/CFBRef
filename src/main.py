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
import state
from classes import QuarterType
from classes import Action

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


if not os.path.exists(globals.SAVE_FOLDER_NAME):
	os.makedirs(globals.SAVE_FOLDER_NAME)


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

while True:
	try:
		for message in reddit.getMessageStream():
			startTime = time.perf_counter()
			log.debug("Processing message")
			wiki.loadPages()

			try:
				messages.processMessage(message)
			except Exception as err:
				log.warning("Error in main loop")
				log.warning(traceback.format_exc())
				if globals.game is not None:
					log.debug("Setting game {} as errored".format(globals.game.thread))
					database.setGameErrored(globals.game.dataID)
					bldr = []
					bldr.append("[Game](")
					bldr.append(globals.SUBREDDIT_LINK)
					bldr.append(globals.logGameId[1:-1])
					bldr.append(") errored.\n\n")
					bldr.append("Status|Waiting|Link\n")
					bldr.append(":-:|:-:|:-:\n")

					for i, status in enumerate(globals.game.previousStatus):
						bldr.append(status.possession.name())
						bldr.append("/")
						bldr.append(globals.game.team(status.possession).name)
						bldr.append(" with ")
						bldr.append(utils.getNthWord(status.down))
						bldr.append(" & ")
						bldr.append(str(status.yards))
						bldr.append(" on the ")
						bldr.append(str(status.location))
						bldr.append(" with ")
						bldr.append(utils.renderTime(status.clock))
						bldr.append(" in the ")
						bldr.append(utils.getNthWord(status.quarter))
						bldr.append("|")
						bldr.append(utils.getLinkFromGameThing(globals.game.thread, status.waitingId))
						bldr.append(" ")
						bldr.append(status.waitingOn.name())
						bldr.append("/")
						bldr.append(globals.game.team(status.waitingOn))
						bldr.append(" for ")
						bldr.append(status.waitingAction.name)
						bldr.append("|")
						bldr.append("[Message](")
						bldr.append(utils.buildMessageLink(
			                        globals.ACCOUNT_NAME,
			                        "Kick game",
			                        "kick {} {}".format(globals.game.thread, i)
			                    ))
						bldr.append(")")

					try:
						ownerMessage = ''.join(bldr)
					except Exception as err:
						log.debug("Couldn't join game error message: ")
						log.debug(str(bldr))
						log.warning(traceback.format_exc())

					message.reply("This game has errored. Please wait for the bot owner to help.")
				else:
					ownerMessage = "Unable to process message from /u/{}, skipping".format(str(message.author))

				try:
					reddit.sendMessage(globals.OWNER, "NCFAA game errored", ownerMessage)
					message.mark_read()
				except Exception as err2:
					log.warning("Error sending error message")
					log.warning(traceback.format_exc())

			for threadId in database.getGamesPastPlayclock():
				log.debug("Game past playclock: {}".format(threadId))
				game = utils.loadGameObject(threadId)
				utils.cycleStatus(game, None)
				game.status.state(game.status.waitingOn).playclockPenalties += 1
				penaltyMessage = "{} has not sent their number in over 24 hours, playclock penalty. This is their {} penalty.".format(
					utils.getCoachString(game, game.status.waitingOn), utils.getNthWord(game.status.state(game.status.waitingOn).playclockPenalties))
				if game.status.state(game.status.waitingOn).playclockPenalties >= 3:
					log.debug("3 penalties, game over")
					game.status.quarterType = QuarterType.END
					game.status.waitingAction = Action.END
					resultMessage = "They forfeit the game. {} has won!".format(utils.flair(game.team(game.status.waitingOn.negate())))

				elif game.status.waitingOn == game.status.possession:
					log.debug("Waiting on offense, turnover")
					if utils.isGameOvertime(game):
						resultMessage = state.overtimeTurnover(game)
						if game.status.waitingAction != Action.END:
							utils.sendDefensiveNumberMessage(game)
					else:
						state.turnover(game)
						utils.sendDefensiveNumberMessage(game)
						resultMessage = "Turnover, {} has the ball.".format(utils.flair(game.team(game.status.waitingOn)))

				else:
					log.debug("Waiting on defense, touchdown")
					if utils.isGameOvertime(game):
						state.forceTouchdown(game, game.status.possession)
						resultMessage = state.overtimeTurnover(game)
						if game.status.waitingAction != Action.END:
							utils.sendDefensiveNumberMessage(game)
					else:
						state.forceTouchdown(game, game.status.possession)
						state.setStateTouchback(game, game.status.possession.negate())
						game.status.waitingOn.reverse()
						utils.sendDefensiveNumberMessage(game)
						resultMessage = "Automatic 7 point touchdown, {} has the ball.".format(utils.flair(game.team(game.status.waitingOn)))

				utils.sendGameComment(game, "{}\n\n{}".format(penaltyMessage, resultMessage), False)
				database.setGamePlayed(game.dataID)
				utils.updateGameThread(game)

			log.debug("Message processed after: %d", int(time.perf_counter() - startTime))
			utils.clearLogGameID()
			if once:
				database.close()
				break

	except Exception as err:
		log.warning("Hit an error in main loop")
		log.warning(traceback.format_exc())

	if once:
		break

	time.sleep(5 * 60)
