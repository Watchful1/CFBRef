import logging.handlers
import re
import time
from datetime import datetime
from datetime import timedelta

import reddit
import globals
import classes
from classes import OffenseType
from classes import DefenseType
from classes import Result
from classes import Play

log = logging.getLogger("bot")

teams = {}
coaches = {}
plays = {}
times = {}
admins = set()

lastTime = None


def loadPages():
	global lastTime
	if lastTime is None or lastTime + timedelta(minutes=15) < datetime.utcnow():
		startTime = time.perf_counter()
		log.debug("Loading pages")
		lastTime = datetime.utcnow()
		loadTeams()
		loadPlays()
		loadTimes()
		loadAdmins()
		log.debug("Done loading pages in: %d", int(time.perf_counter() - startTime))


def validateItem(playItem, regex):
	return re.match(regex, playItem) is not None


def parseOffense(offenseString):
	offenseString = offenseString.lower()
	if "option" in offenseString:
		return OffenseType.OPTION
	elif "spread" in offenseString:
		return OffenseType.SPREAD
	elif "pro" in offenseString:
		return OffenseType.PRO
	else:
		return None


def parseDefense(defenseString):
	defenseString = defenseString.lower()
	if "3-4" in defenseString:
		return DefenseType.THREE_FOUR
	elif "4-3" in defenseString:
		return DefenseType.FOUR_THREE
	elif "5-2" in defenseString:
		return DefenseType.FIVE_TWO
	else:
		return None


def loadTeams():
	teamsPage = reddit.getWikiPage(globals.CONFIG_SUBREDDIT, "teams")

	requirements = {
		'tag': "[a-z]+",
		'name': "[\w -]+",
	}
	for teamLine in teamsPage.splitlines():
		items = teamLine.split('|')
		if len(items) < 5:
			log.warning("Could not parse team line: {}".format(teamLine))
			continue

		offense = parseOffense(items[2].lower())
		if offense is None:
			log.warning("Invalid offense type for team {}: {}".format(items[0], items[2]))
			continue

		defense = parseDefense(items[3].lower())
		if defense is None:
			log.warning("Invalid defense type for team {}: {}".format(items[0], items[2]))
			continue

		team = classes.Team(tag=items[0], name=items[1], offense=offense, defense=defense)

		for requirement in requirements:
			if not validateItem(getattr(team, requirement), requirements[requirement]):
				log.debug("Could not validate team on {}: {}".format(requirement, team))
				continue

		for coach in items[4].lower().split(','):
			coach = coach.strip()
			team.coaches.append(coach)
			coaches[coach] = team
		teams[team.tag] = team


def initOffenseDefense(play, offense, defense, range):
	if not initRange(play, range):
		return False

	if offense not in plays[play]:
		plays[play][offense] = {}

	if defense not in plays[play][offense]:
		plays[play][offense][defense] = {}
	return True


def initRange(play, range):
	if not validateItem(play, "\w{3,12}"):
		log.warning("Bad play item: {}".format(play))
		return False
	if not validateItem(range, "\d+-\d+"):
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
	if not validateItem(range, "\d+-\d+"):
		log.warning("Could not validate range: {}".format(range))
		return None, None

	result = parts[1]
	if result == "gain":
		result = Result.GAIN
	elif result == "turnover":
		result = Result.TURNOVER
	elif result == "touchdown":
		result = Result.TOUCHDOWN
	elif result == "turnoverTouchdown":
		result = Result.TURNOVER_TOUCHDOWN
	elif result == "incomplete":
		result = Result.INCOMPLETE
	elif result == "touchback":
		result = Result.TOUCHBACK
	elif result == "fieldGoal":
		result = Result.FIELD_GOAL
	elif result == "miss":
		result = Result.MISS
	elif result == "pat":
		result = Result.PAT
	elif result == "twoPoint":
		result = Result.TWO_POINT
	elif result == "kickoff":
		result = Result.KICKOFF
	elif result == "punt":
		result = Result.PUNT
	elif result == "kick":
		result = Result.KICK
	else:
		log.warning("Could not validate result: {}".format(result))
		return None, None

	play = {'result': result}

	if len(parts) > 2:
		if not validateItem(parts[2], "-?\d+"):
			log.warning("Could not validate yards: {}".format(parts[2]))
			return None, None
		play['yards'] = int(parts[2])

	return range, play


def loadPlays():
	playsPage = reddit.getWikiPage(globals.CONFIG_SUBREDDIT, "plays")

	for playLine in playsPage.splitlines():
		items = playLine.split('|')
		isMovementPlay = items[0] in globals.movementPlays

		offense = None
		defense = None
		if isMovementPlay:
			startIndex = 4

			offense = parseOffense(items[1])
			if offense is None:
				log.warning("Bad offense item: {}".format(items[1]))
				continue

			defense = parseDefense(items[2])
			if defense is None:
				log.warning("Bad defense item: {}".format(items[2]))
				continue

			if not initOffenseDefense(items[0], offense, defense, items[3]):
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
			plays[items[0]][offense][defense][items[3]] = playParts
		else:
			plays[items[0]][items[1]] = playParts


def loadTimes():
	timesPage = reddit.getWikiPage(globals.CONFIG_SUBREDDIT, "times")

	for timeLine in timesPage.splitlines():
		items = timeLine.split('|')
		if items[0] not in times:
			times[items[0]] = {}

		for item in items[1:]:
			timePart = item.split(",")

			result = timePart[0]
			if result == "gain":
				result = Result.GAIN
			if result == "turnover":
				result = Result.TURNOVER
			if result == "turnoverTouchdown":
				result = Result.TURNOVER_TOUCHDOWN
			if result == "touchdown":
				result = Result.TOUCHDOWN
			if result == "incomplete":
				result = Result.INCOMPLETE
			if result == "fieldGoal":
				result = Result.FIELD_GOAL
			if result == "kick":
				result = Result.KICK
			if result == "touchback":
				result = Result.TOUCHBACK
			else:
				log.warning("Could not validate result: {}".format(result))
				continue

			if result in ['gain', 'kick']:
				if not validateItem(timePart[1], "-?\d+"):
					log.warning("Could not validate time yards: {}".format(timePart[1]))
					continue
				if not validateItem(timePart[2], "\d+"):
					log.warning("Could not validate time: {}".format(timePart[2]))
					continue

				if result not in times[items[0]]:
					times[items[0]][result] = []
				timeObject = {'yards': int(timePart[1]), 'time': int(timePart[2])}
				times[items[0]][result].append(timeObject)
			else:
				if not validateItem(timePart[1], "\d+"):
					log.warning("Could not validate time: {}".format(timePart[1]))
					continue

				timeObject = {'time': int(timePart[1])}
				times[items[0]][result] = timeObject


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


def getTimeByPlay(play):
	if play in times:
		return times[play]
	else:
		return None


def loadAdmins():
	adminsPage = reddit.getWikiPage(globals.CONFIG_SUBREDDIT, "admins")

	for line in adminsPage.splitlines():
		admins.add(line.lower())

	admins.add(globals.OWNER)
