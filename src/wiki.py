import logging.handlers
import re

import reddit
import globals
import utils

log = logging.getLogger("bot")

teams = {}
coaches = {}
plays = {}


def loadTeams(debug=False):
	teamsPage = reddit.getWikiPage(globals.CONFIG_SUBREDDIT, "teams")

	if debug:
		teamsPage = "\n".join([teamsPage,
		                       "testteam|Test Team|Spread|3-4|Watchful1",
		                       "testteam2|Test Team 2|Spread|3-4|Watchful12"])

	for teamLine in teamsPage.splitlines():
		items = teamLine.split('|')
		if len(items) < 5:
			log.warning("Could not parse team line: {}".format(teamLine))
			continue
		team = {'tag': items[0], 'name': items[1], 'offense': items[2].lower(), 'defense': items[3].lower(),
		        'coaches': []}
		for coach in items[4].lower().split(','):
			coach = coach.strip()
			team['coaches'].append(coach)
			coaches[coach] = team
		teams[team['tag']] = team


def validatePlayItem(playItem, regex):
	return re.match(regex, playItem) is not None


def initOffenseDefense(play, offense, defense, range):
	if not initRange(play, range):
		return False
	if not validatePlayItem(offense, "\w{3,7}"):
		log.warning("Bad offense item: {}".format(offense))
		return False
	if offense not in plays[play]:
		plays[play][offense] = {}
	if not validatePlayItem(defense, "\d-\d"):
		log.warning("Bad defense item: {}".format(defense))
		return False
	if defense not in plays[play][offense]:
		plays[play][offense][defense] = {}
	return True


def initRange(play, range):
	if not validatePlayItem(play, "\w{3,12}"):
		log.warning("Bad play item: {}".format(play))
		return False
	if not validatePlayItem(range, "\d+-\d+"):
		log.warning("Bad range item: {}".format(range))
		return False
	if play not in plays:
		plays[play] = {}
	return True


def parsePlayPart(playPart):
	parts = playPart.split(',')
	if len(parts) < 2:
		log.warning("Could not parse play part: {}".format(playPart))
		return None, None

	range = parts[0]
	if not validatePlayItem(range, "\d+-\d+"):
		log.warning("Could not validate range: {}".format(range))
		return None, None

	result = parts[1]
	if not validatePlayItem(result, "\w{3,20}"):
		log.warning("Could not validate result: {}".format(result))
		return None, None

	play = {'result': result}

	if len(parts) > 2:
		if not validatePlayItem(parts[2], "-?\d+"):
			log.warning("Could not validate yards: {}".format(parts[2]))
			return None, None
		play['yards'] = int(parts[2])

	return range, play


def loadPlays():
	playsPage = reddit.getWikiPage(globals.CONFIG_SUBREDDIT, "plays")

	for playLine in playsPage.splitlines():
		items = playLine.split('|')
		isMovementPlay = items[0] in globals.movementPlays

		if isMovementPlay:
			startIndex = 4
			if not initOffenseDefense(items[0], items[1], items[2], items[3]):
				log.warning("Could not parse play: {}".format(playLine))
				continue
		else:
			startIndex = 2
			if not initRange(items[0], items[1]):
				log.warning("Could not parse play: {}".format(playLine))
				continue

		playParts = {}
		for item in items[startIndex:]:
			range, play = parsePlayPart(item)
			if play is None:
				continue
			playParts[range] = play

		if isMovementPlay:
			plays[items[0]][items[1]][items[2]][items[3]] = playParts
		else:
			plays[items[0]][items[1]] = playParts


def getTeamByTag(tag):
	tag = tag.lower()
	if tag in teams:
		return teams[tag]
	else:
		return None


def getTeamByCoach(coach):
	coach = coach.lower()
	if coach in coaches:
		return coaches[coach]
	else:
		return None


def getPlay(play):
	if play in plays:
		return plays[play]
	else:
		return None
