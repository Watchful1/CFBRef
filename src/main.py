#!/usr/bin/python3

import os
import logging.handlers
import time
import sys
import signal
import traceback
import discord_logging
from datetime import datetime

import static
import reddit
import messages
import wiki
import utils
import state
import index
import file_utils
import string_utils
import drive_graphic
import counters
import coach_stats
from classes import Action


class ContextFilter(logging.Filter):
	def filter(self, record):
		record.gameid = static.logGameId
		return True


log = discord_logging.init_logging(
	backup_count=20,
	debug=True,
	format_string='%(asctime)s - %(levelname)s:%(gameid)s %(message)s'
)
log.addFilter(ContextFilter())


if not os.path.exists(static.SAVE_FOLDER_NAME):
	os.makedirs(static.SAVE_FOLDER_NAME)
if not os.path.exists(static.ARCHIVE_FOLDER_NAME):
	os.makedirs(static.ARCHIVE_FOLDER_NAME)


def signal_handler(signal, frame):
	log.info("Handling interupt")
	coach_stats.close()
	sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


log.debug("Connecting to reddit")

once = False
debug = False
user = None
update_wiki = False
if len(sys.argv) >= 2:
	user = sys.argv[1]
	for arg in sys.argv:
		if arg == 'once':
			once = True
		elif arg == 'debug':
			debug = True
		elif arg == 'shortQuarter':
			static.quarterLength = 60
		elif arg == 'updateWiki':
			update_wiki = True
else:
	log.error("No user specified, aborting")
	sys.exit(0)

discord_logging.init_discord_logging(user, logging.WARNING, 1)

if not reddit.init(user):
	sys.exit(0)

counters.init(8002)

wiki.loadPages()

index.init()

drive_graphic.init()

if update_wiki:
	wiki.updateTeamsWiki()

coach_stats.init("database.db")

while True:
	try:
		for message in reddit.getMessageStream():
			startTime = time.perf_counter()

			log.debug(
				f"Processing message: "
				f"{(datetime.utcnow() - datetime.utcfromtimestamp(message.created_utc)).total_seconds()}")
			wiki.loadPages()

			try:
				messages.processMessage(message)
				counters.objects_replied.inc()
			except Exception as err:
				log.warning("Error in main loop")
				log.warning(traceback.format_exc())
				if static.game is not None:
					log.debug("Setting game {} as errored".format(static.game.thread))
					index.setGameErrored(static.game)
					file_utils.saveGameObject(static.game)
					ownerMessage = string_utils.renderGameStatusMessage(static.game)

					message.reply("This game has errored. Please wait for the bot owner to help.")
				else:
					ownerMessage = "Unable to process message from /u/{}, skipping".format(str(message.author))

				try:
					reddit.sendMessage(static.OWNER, "NCFAA game errored", ownerMessage)
					message.mark_read()
				except Exception as err2:
					log.warning("Error sending error message")
					log.warning(traceback.format_exc())

			log.debug("Message processed after: %d", int(time.perf_counter() - startTime))
			utils.clearLogGameID()

			for game in index.getGamesPastPlayclock():
				state.executeDelayOfGame(game)
				if game.status.waitingAction == Action.END:
					index.endGame(game)

			for game in index.getGamesPastPlayclockWarning():
				warningText = "This is a warning that your [game]({}) is waiting on a reply from you to " \
								"this {}. You have 12 hours until a delay of game penalty."\
								.format(string_utils.getLinkToThread(game.thread),
				                        string_utils.getLinkFromGameThing(game.thread, utils.getPrimaryWaitingId(game.status.waitingId)))
				results = reddit.sendMessage(recipients=game.team(game.status.waitingOn).coaches,
									subject="{} vs {} 12 hour warning".format(game.away.name, game.home.name),
									message=warningText)
				log.debug("12 hour warning sent to {} for game {}: {}"
							.format(
							string_utils.getCoachString(game, game.status.waitingOn),
							game.thread,
							','.join([result.fullname for result in results])
						))
				game.playclockWarning = True
				file_utils.saveGameObject(game)

			utils.clearLogGameID()
			if once:
				break

	except Exception as err:
		log.warning("Hit an error in main loop")
		log.warning(traceback.format_exc())

	if once:
		break

	time.sleep(5 * 60)
