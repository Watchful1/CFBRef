import logging.handlers
import pickle
import os
import traceback

import static

log = logging.getLogger("bot")


def saveGameObject(game):
	file = open("{}/{}".format(static.SAVE_FOLDER_NAME, game.thread), 'wb')
	pickle.dump(game, file)
	file.close()


def loadGameObject(threadID):
	try:
		file = open("{}/{}".format(static.SAVE_FOLDER_NAME, threadID), 'rb')
	except FileNotFoundError as err:
		log.warning("Game file doesn't exist: {}".format(threadID))
		return None
	game = pickle.load(file)
	file.close()
	return game


def archiveGameFile(threadID):
	log.debug("Archiving game: {}".format(threadID))
	sourcePath = "{}/{}".format(static.SAVE_FOLDER_NAME, threadID)
	destinationPath = "{}/{}".format(static.ARCHIVE_FOLDER_NAME, threadID)
	if os.path.exists(destinationPath):
		log.info("Game already exists in archive, deleting")
		os.remove(destinationPath)
	try:
		os.rename(sourcePath, destinationPath)
	except Exception as err:
		log.warning("Can't archive game file: {}".format(threadID))
		log.warning(traceback.format_exc())
		return False
	return True


def saveStringSuggestion(stringKey, suggestion):
	with open(static.STRING_SUGGESTION_FILE, 'a') as fileHandle:
		fileHandle.write(stringKey)
		fileHandle.write(": ")
		fileHandle.write(suggestion)
		fileHandle.write("\n")
		fileHandle.write("----------------------------------------\n")


def saveRestartReason(threadId, reason):
	with open(static.RESTART_REASON_FILE, 'a') as fileHandle:
		fileHandle.write(threadId)
		fileHandle.write(": ")
		fileHandle.write(reason)
		fileHandle.write("\n")


def saveTeams(teams):
	file = open(static.TEAMS_FILE, 'wb')
	pickle.dump(teams, file)
	file.close()


def loadTeams():
	try:
		file = open(static.TEAMS_FILE, 'rb')
	except FileNotFoundError as err:
		log.info("Teams file doesn't exist, returning empty")
		return {}
	teams = pickle.load(file)
	file.close()
	return teams
