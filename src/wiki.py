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
from classes import Team
from classes import Play

log = logging.getLogger("bot")

teams = {}
coaches = {}
plays = {}
times = {}
admins = set()

lastTime = None


def loadPages(force=False):
	global lastTime
	if force or lastTime is None or lastTime + timedelta(minutes=15) < datetime.utcnow():
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


def parsePlay(playString):
	if playString == "run":
		return Play.RUN
	elif playString == "pass":
		return Play.PASS
	elif playString == "fieldGoal":
		return Play.FIELD_GOAL
	elif playString == "pat":
		return Play.PAT
	elif playString == "twoPoint":
		return Play.TWO_POINT
	elif playString == "punt":
		return Play.PUNT
	elif playString == "kickoffNormal":
		return Play.KICKOFF_NORMAL
	elif playString == "kickoffSquib":
		return Play.KICKOFF_SQUIB
	elif playString == "kickoffOnside":
		return Play.KICKOFF_ONSIDE
	else:
		return None


def parseResult(resultString):
	if resultString == "gain":
		return Result.GAIN
	elif resultString == "turnover":
		return Result.TURNOVER
	elif resultString == "touchdown":
		return Result.TOUCHDOWN
	elif resultString == "turnoverTouchdown":
		return Result.TURNOVER_TOUCHDOWN
	elif resultString == "incomplete":
		return Result.INCOMPLETE
	elif resultString == "touchback":
		return Result.TOUCHBACK
	elif resultString == "fieldGoal":
		return Result.FIELD_GOAL
	elif resultString == "miss":
		return Result.MISS
	elif resultString == "pat":
		return Result.PAT
	elif resultString == "twoPoint":
		return Result.TWO_POINT
	elif resultString == "kickoff":
		return Result.KICKOFF
	elif resultString == "punt":
		return Result.PUNT
	elif resultString == "kick":
		return Result.KICK
	else:
		return None


def loadTeams():
	global teams
	teams = {}
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

		team = Team(tag=items[0], name=items[1], offense=offense, defense=defense)

		for requirement in requirements:
			if not validateItem(getattr(team, requirement), requirements[requirement]):
				log.debug("Could not validate team on {}: {}".format(requirement, team))
				continue

		for coach in items[4].lower().split(','):
			coach = coach.strip()
			team.coaches.append(coach)
		teams[team.tag] = team

	coach1 = "watchful1"
	team1 = Team(tag="team1", name="Team 1", offense=OffenseType.OPTION, defense=DefenseType.THREE_FOUR)
	team1.coaches.append(coach1)
	teams[team1.tag] = team1

	coach2 = "watchful12"
	team2 = Team(tag="team2", name="Team 2", offense=OffenseType.SPREAD, defense=DefenseType.FOUR_THREE)
	team2.coaches.append(coach2)
	teams[team2.tag] = team2


def initOffenseDefense(play, offense, defense, range):
	if not initRange(play, range):
		return False

	if offense not in plays[play]:
		plays[play][offense] = {}

	if defense not in plays[play][offense]:
		plays[play][offense][defense] = {}
	return True


def initRange(play, range):
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

	result = parseResult(parts[1])
	if result is None:
		log.warning("Could not validate result in plays: {}".format(parts[1]))
		return None, None

	play = {'result': result}

	if len(parts) > 2:
		if not validateItem(parts[2], "-?\d+"):
			log.warning("Could not validate yards: {}".format(parts[2]))
			return None, None
		play['yards'] = int(parts[2])

	return range, play


def loadPlays():
	global plays
	plays = {}
	playsPage = reddit.getWikiPage(globals.CONFIG_SUBREDDIT, "plays")

	for playLine in playsPage.splitlines():
		items = playLine.split('|')

		playType = parsePlay(items[0])
		if playType is None:
			log.warning("Could not parse play: {}".format(playLine))
			continue

		isMovementPlay = playType in [Play.RUN, Play.PASS]

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

			if not initOffenseDefense(playType, offense, defense, items[3]):
				log.warning("Could not parse play: {}".format(playLine))
				continue
		else:
			startIndex = 2
			if not initRange(playType, items[1]):
				log.warning("Could not parse play: {}".format(playLine))
				continue

		playParts = {}
		for item in items[startIndex:]:
			range, play = parsePlayPart(item)
			if play is None:
				continue
			playParts[range] = play

		if isMovementPlay:
			plays[playType][offense][defense][items[3]] = playParts
		else:
			plays[playType][items[1]] = playParts


def loadTimes():
	global times
	times = {}
	timesPage = reddit.getWikiPage(globals.CONFIG_SUBREDDIT, "times")

	for timeLine in timesPage.splitlines():
		items = timeLine.split('|')

		playType = parsePlay(items[0])
		if playType is None:
			log.warning("Could not parse play: {}".format(timeLine))
			continue

		if playType not in times:
			times[playType] = {}

		for item in items[1:]:
			timePart = item.split(",")

			result = parseResult(timePart[0])
			if result is None:
				log.warning("Could not validate result in times: {}".format(timePart[1]))
				continue

			if result in [Result.GAIN, Result.KICK]:
				if not validateItem(timePart[1], "-?\d+"):
					log.warning("Could not validate time yards: {}".format(timePart[1]))
					continue
				if not validateItem(timePart[2], "\d+"):
					log.warning("Could not validate time: {}".format(timePart[2]))
					continue

				if result not in times[playType]:
					times[playType][result] = []
				timeObject = {'yards': int(timePart[1]), 'time': int(timePart[2])}
				times[playType][result].append(timeObject)
			else:
				if not validateItem(timePart[1], "\d+"):
					log.warning("Could not validate time: {}".format(timePart[1]))
					continue

				timeObject = {'time': int(timePart[1])}
				times[playType][result] = timeObject


def getTeamByTag(tag):
	tag = tag.lower()
	if tag in teams:
		return teams[tag]
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
