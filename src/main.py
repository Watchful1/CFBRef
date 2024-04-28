import os
import logging.handlers
import time
import sys
import signal
import traceback
import discord_logging
import praw
from datetime import datetime, timedelta

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
from classes import Action, PlayclockWarning, Queue


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


def signal_handler(signal, frame):
	log.info("Handling interupt")
	coach_stats.close()
	discord_logging.flush_discord()
	sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


def handle_message(message):
	startTime = time.perf_counter()

	log.debug(
		f"Processing message: "
		f"{(datetime.utcnow() - datetime.utcfromtimestamp(message.created_utc)).total_seconds()}")

	try:
		if isinstance(message, praw.models.Comment):
			recently_processed_comments.put(message.id)

		messages.processMessage(message)
		counters.objects_replied.inc()
	except Exception as err:
		if utils.error_is_transient(err):
			log.warning(f"Transient error, sleeping: {err}")
			log.warning(traceback.format_exc())
			time.sleep(180)
		else:
			log.warning(f"Error processing message: {err}")
			log.warning(traceback.format_exc())
		if static.game is not None:
			log.debug("Setting game {} as errored".format(static.game.thread))
			index.setGameErrored(static.game)
			file_utils.saveGameObject(static.game)

			message.reply(string_utils.renderErrorMessage())

		try:
			message.mark_read()
		except Exception as err2:
			log.warning("Error marking errored game message as read")
			log.warning(traceback.format_exc())

	log.debug("Message processed after: %d", int(time.perf_counter() - startTime))
	utils.clearLogGameID()


if __name__ == "__main__":
	if not os.path.exists(static.SAVE_FOLDER_NAME):
		os.makedirs(static.SAVE_FOLDER_NAME)
	if not os.path.exists(static.ARCHIVE_FOLDER_NAME):
		os.makedirs(static.ARCHIVE_FOLDER_NAME)

	log.debug("Connecting to reddit")

	once = False
	debug = False
	user = None
	update_wiki = False
	no_wiki = False
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
			elif arg == 'noWriteWiki':
				no_wiki = True
	else:
		log.error("No user specified, aborting")
		sys.exit(0)

	discord_logging.init_discord_logging(user, logging.WARNING, 1)

	if not reddit.init(user):
		sys.exit(0)

	reddit.noWrite = no_wiki

	counters.init(8002)

	wiki.loadPages()

	index.init()

	drive_graphic.init()

	coach_stats.init("database.db")

	if update_wiki:
		wiki.updateTeamsWiki()
		wiki.updateCoachesWiki()
		wiki.updateGamesWiki()

	count_messages = 0
	comments_checked = None
	recently_processed_comments = Queue(200)
	while True:
		try:
			for message in reddit.getMessageStream():
				wiki.loadPages()
				count_messages += 1

				if isinstance(message, praw.models.Comment) and not recently_processed_comments.contains(message.id):
					recently_processed_comments.put(message.id)
				handle_message(message)

				for game in index.getGamesPastPlayclock():
					state.executeDelayOfGame(game)
					if game.status.waitingAction == Action.END:
						index.endGame(game)

				try:
					for warning, hours, game in index.getGamesPastPlayclockWarning():
						warningText = \
							"This is a warning that your [game]({}) is waiting on a reply from you to " \
							"this {}. You have {} hours until a delay of game penalty."\
							.format(
								string_utils.getLinkToThread(game.thread),
								string_utils.getLinkFromGameThing(game.thread, utils.getPrimaryWaitingId(game.status.waitingId)),
								hours)
						try:
							results = reddit.sendMessage(
								recipients=game.team(game.status.waitingOn).coaches,
								subject="{} vs {} {} hour warning".format(game.away.name, game.home.name, hours),
								message=warningText)
						except Exception as err:
							log.warning(f"Error sending {hours} hour warning message to {game.team(game.status.waitingOn).coaches}")
						log.debug(
							"{} hour warning sent to {} for game {}: {}"
							.format(
								hours,
								string_utils.getCoachString(game, game.status.waitingOn),
								game.thread,
								','.join([result.fullname for result in results])
							)
						)
						game.playclockWarning = warning
						file_utils.saveGameObject(game)
				except Exception as e:
					log.warning(f"Exception sending warning messages: {e}")

				counters.gist_queue.set(len(static.GIST_PENDING))
				if (not static.GIST_LIMITED or datetime.utcnow() > static.GIST_RESET) and len(static.GIST_PENDING):
					log.info(f"Resending gists: {static.GIST_LIMITED} : {static.GIST_RESET} : {len(static.GIST_PENDING)}")
					for thread in list(static.GIST_PENDING):
						game = index.reloadAndReturn(thread)
						if game is None:
							log.warning(f"Game for thread doesn't exist: {thread}")
							static.GIST_PENDING.remove(thread)
							continue
						log.info(f"Resending gist: {game.thread} : {game.playGist}")
						if game is not None:
							utils.paste_plays(game)
							file_utils.saveGameObject(game)

				utils.clearLogGameID()

				if comments_checked is None:
					for comment in reddit.getSubredditComments(static.SUBREDDIT):
						if comment.author.name.lower() == "nfcaaofficialrefbot":
							continue
						recently_processed_comments.put(comment.id)

					comments_checked = datetime.utcnow()

				try:
					if comments_checked < datetime.utcnow() - timedelta(minutes=2):
						for comment in reddit.getSubredditComments(static.SUBREDDIT):
							if recently_processed_comments.contains(comment.id):
								continue
							if datetime.utcfromtimestamp(comment.created_utc) > datetime.utcnow() - timedelta(minutes=1):
								continue
							if comment.author.name.lower() == "nfcaaofficialrefbot":
								continue
							recently_processed_comments.put(comment.id)
							if comment.parent().author.name.lower() != "nfcaaofficialrefbot":
								continue
							log.warning(f"Handling missed comment: <https://www.reddit.com{comment.permalink}?context=9>")
							handle_message(comment)
							count_messages += 1

						comments_checked = datetime.utcnow()
				except Exception as e:
					log.warning(f"Exception checking subreddit comments: {e}")

				if count_messages % 50 == 0:
					wiki.updateCoachesWiki()
					wiki.updateGamesWiki()

				discord_logging.flush_discord()

				if once:
					break

		except Exception as err:
			utils.process_error(f"Hit an error in main loop", err, traceback.format_exc())

		discord_logging.flush_discord()

		if once:
			break

		time.sleep(5 * 60)
