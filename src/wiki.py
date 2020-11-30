import logging.handlers
import re
import time
import random
import csv
from datetime import datetime
from datetime import timedelta
from collections import defaultdict

import reddit
import static
import string_utils
import file_utils
import coach_stats
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
intro = "Welcome to /r/FakeCollegeFootball!"
strings = {}

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
		loadIntro()
		loadStrings()
		log.debug("Done loading pages in: %d", int(time.perf_counter() - startTime))


def validateItem(playItem, regex):
	return re.match(regex, playItem) is not None


def parseOffense(offenseString):
	offenseString = offenseString.lower()
	if "option" == offenseString or "flexbone" == offenseString:
		return OffenseType.FLEXBONE
	elif "spread" == offenseString:
		return OffenseType.SPREAD
	elif "pro" == offenseString:
		return OffenseType.PRO
	elif "air" == offenseString:
		return OffenseType.AIR
	elif "pistol" == offenseString or "westcoast" == offenseString:
		return OffenseType.PISTOL
	else:
		return None


def parseDefense(defenseString):
	defenseString = defenseString.lower()
	if "3-4" == defenseString:
		return DefenseType.THREE_FOUR
	elif "4-3" == defenseString:
		return DefenseType.FOUR_THREE
	elif "5-2" == defenseString:
		return DefenseType.FIVE_TWO
	elif "4-4" == defenseString:
		return DefenseType.FOUR_FOUR
	elif "3-3-5" == defenseString:
		return DefenseType.THREE_THREE_FIVE
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
	elif resultString == "turnoverPat":
		return Result.TURNOVER_PAT
	else:
		return None


def parseTeamLine(teamLine):
	requirements = {
		'tag': r"[a-z]+",
		'name': r"[\w -]+",
	}
	items = teamLine.split('|')
	if len(items) < 7:
		log.warning("Could not parse team line: {}".format(teamLine))
		return None, "Not enough items"

	offense = parseOffense(items[2].lower())
	if offense is None:
		log.warning("Invalid offense type for team {}: {}".format(items[0], items[2]))
		return None, "Invalid offense type for team {}: {}".format(items[0], items[2])

	defense = parseDefense(items[3].lower())
	if defense is None:
		log.warning("Invalid defense type for team {}: {}".format(items[0], items[2]))
		return None, "Invalid defense type for team {}: {}".format(items[0], items[2])

	team = Team(tag=items[0], name=items[1], offense=offense, defense=defense)

	for requirement in requirements:
		if not validateItem(getattr(team, requirement), requirements[requirement]):
			log.debug("Could not validate team on {}: {}".format(requirement, team))
			return None, f"Field {requirement} does not match regex {requirements[requirement]}"

	for coach in items[4].lower().split(','):
		coach = coach.strip()
		team.coaches.append(coach)

	if items[5] != "":
		team.conference = items[5]

	if items[6] != "":
		team.css_tag = items[6]

	return team, None


def loadTeams():
	global teams
	teams = file_utils.loadTeams()


def updateTeamsWiki():
	teamsWikiString = string_utils.renderTeamsWiki(teams)
	reddit.setWikiPage(static.SUBREDDIT, "teams", teamsWikiString)


def updateCoachesWiki():
	coach_stats.delete_old_stats()
	coachesWikiString = string_utils.renderCoachesWiki(coach_stats.getCoaches())
	reddit.setWikiPage(static.SUBREDDIT, "coaches", coachesWikiString)


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
	parts = playPart.split('|')
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
	with open("data/plays.csv", 'r') as playsFile:
		playsPage = playsFile.readlines()

	for playLine in playsPage[1:]:
		items = playLine.strip().split(',')
		items = list(filter(None, items))

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
		previousMax = 751
		for item in items[startIndex:]:
			range, play = parsePlayPart(item)
			if play is None:
				log.warning(f"Could not parse play part: {item}")
				continue
			rangeParts = range.split("-")
			if not len(rangeParts) == 2:
				log.warning(f"Bad range: {range}")
				continue
			if previousMax - 1 != int(rangeParts[1]):
				log.warning(f"Bad range max, {range}, expecting {previousMax}")
			previousMax = int(rangeParts[0])
			playParts[range] = play

		if previousMax != 0:
			log.warning(f"After parsing ranges, ended on {previousMax}")

		if isMovementPlay:
			plays[playType][offense][defense][items[3]] = playParts
		else:
			plays[playType][items[1]] = playParts


def loadTimes():
	global times
	times = {}
	with open("data/times.csv", 'r') as timesFile:
		timesPage = timesFile.readlines()

	for timeLine in timesPage[1:]:
		items = timeLine.strip().split(',')
		items = list(filter(None, items))

		playType = parsePlay(items[0])
		if playType is None:
			log.warning("Could not parse play: {}".format(timeLine))
			continue

		if playType not in times:
			times[playType] = {}

		for item in items[1:]:
			timePart = item.split("|")

			result = parseResult(timePart[0])
			if result is None:
				log.warning("Could not validate result in times: {}".format(timePart[1]))
				continue

			if result in [Result.GAIN, Result.KICK]:
				if not validateItem(timePart[1], r"-?\d+"):
					log.warning("Could not validate time yards: {}".format(timePart[1]))
					continue
				if not validateItem(timePart[2], r"\d+"):
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
	adminsPage = reddit.getWikiPage(static.CONFIG_SUBREDDIT, "admins")

	for line in adminsPage.splitlines():
		admins.add(line.lower())

	admins.add(static.OWNER)


def loadIntro():
	global intro
	intro = reddit.getWikiPage(static.CONFIG_SUBREDDIT, "intro")


def loadStrings():
	global strings
	strings = defaultdict(list)
	with open("data/strings.csv", 'r') as stringsFile:
		csv_reader = csv.reader(stringsFile, delimiter=",")
		next(csv_reader)  # skip the headers
		for row in csv_reader:
			if row[2] == '':
				probability = None
			else:
				probability = int(row[2])
			if row[3] == '':
				yards = None
			else:
				yards = int(row[3])
			strings[row[0]].append({'value': row[1], 'probability': probability, 'yards': yards})


def getStringFromKey(stringKey, yards=None, repl=None):
	if stringKey not in strings:
		log.warning(f"Tried to fetch key that doesn't exist {stringKey}")
		return f"Key not found {stringKey}"

	stringValues = []
	existingProbabilities = 0
	countNoProbability = 0
	for stringValue in strings[stringKey]:
		if yards is None or stringValue['yards'] is None or yards >= stringValue['yards']:
			stringValues.append(stringValue)
			if stringValue['probability'] is not None:
				existingProbabilities += stringValue['probability']
			else:
				countNoProbability += 1

	choices = []
	probabilities = []
	splitProbability = 100 / (len(stringValues) - countNoProbability)
	sumProbabilities = 0
	for stringValue in stringValues:
		choices.append(stringValue['value'])
		if stringValue['probability'] is not None:
			probability = stringValue['probability']
		else:
			probability = splitProbability
		probabilities.append(probability)
		sumProbabilities += probability

	if sumProbabilities != 100:
		log.warning(f"Probabilities didn't sum to 100: {sumProbabilities} : {stringKey}")

	choice = random.choices(choices, probabilities)[0]

	if repl is None:
		repl = {}
	repl['yards'] = yards

	bldr = []
	try:
		bldr.append(choice.format(**repl))
	except Exception as err:
		log.warning(f"Could not format string: {stringKey} : {str(repl)}")
		log.warning(f"Choice: {choice}")
		return choice

	bldr.append("^[(!)](")
	bldr.append(string_utils.buildMessageLink(
		static.ACCOUNT_NAME,
		f"suggestion {stringKey}",
		choice
		))
	bldr.append(")")
	return ''.join(bldr)
