import logging.handlers
import json
import traceback
import math
import pytz
import urllib.parse
from datetime import datetime
from collections import defaultdict

import static
import utils
import index
from classes import Action
from classes import QuarterType
from classes import OffenseType
from classes import DefenseType

log = logging.getLogger("bot")


def getLinkToThread(threadID):
	return static.SUBREDDIT_LINK + threadID


PUBLIC_ENUMS = {
	'Action': Action
}


class EnumEncoder(json.JSONEncoder):
	def default(self, obj):
		for enum in PUBLIC_ENUMS.values():
			if type(obj) is enum:
				return {"__enum__": str(obj)}
		return json.JSONEncoder.default(self, obj)


def as_enum(d):
	if "__enum__" in d:
		name, member = d["__enum__"].split(".")
		return getattr(PUBLIC_ENUMS[name], member)
	else:
		return d


def embedTableInMessage(message, table):
	if table is None:
		return message
	else:
		return "{}{}{})".format(message, static.datatag, json.dumps(table, cls=EnumEncoder).replace(" ", "%20"))


def extractTableFromMessage(message):
	datatagLocation = message.find(static.datatag)
	if datatagLocation == -1:
		return None
	data = message[datatagLocation + len(static.datatag):-1].replace("%20", " ")
	try:
		table = json.loads(data, object_hook=as_enum)
		return table
	except Exception:
		log.debug(traceback.format_exc())
		return None


markdown = [
	{'value': "[", 'result': "%5B"},
	{'value': "]", 'result': "%5D"},
	{'value': "(", 'result': "%28"},
	{'value': ")", 'result': "%29"},
]


def escapeMarkdown(value):
	for replacement in markdown:
		value = value.replace(replacement['value'], replacement['result'])
	return value


def unescapeMarkdown(value):
	for replacement in markdown:
		value = value.replace(replacement['result'], replacement['value'])
	return value


def flair(team):
	bldr = []
	bldr.append("[")
	bldr.append(team.name)
	bldr.append("](#f/")
	bldr.append(team.tag)
	if team.css_tag is not None:
		bldr.append("-")
		bldr.append(team.css_tag)
	bldr.append(")")
	return ''.join(bldr)


def renderTime(time):
	if time < 0:
		return "0:00"
	else:
		return "{}:{}".format(str(math.trunc(time / 60)), str(time % 60).zfill(2))


def renderBallLocation(game, useFlair):
	if game.status.location < 50:
		if useFlair:
			return "{} {}".format(str(game.status.location), flair(game.team(game.status.possession)))
		else:
			return "{} {}".format(game.team(game.status.possession).name, str(game.status.location))
	elif game.status.location > 50:
		if useFlair:
			return "{} {}".format(str(100 - game.status.location), flair(game.team(game.status.possession.negate())))
		else:
			return "{} {}".format(game.team(game.status.possession.negate()).name, str(100 - game.status.location))
	else:
		return str(game.status.location)


def renderGameInfo(game, bldr):
	bldr.append(flair(game.away))
	bldr.append(" **")
	bldr.append(game.away.name)
	bldr.append("** @ ")
	bldr.append(flair(game.home))
	bldr.append(" **")
	bldr.append(game.home.name)
	bldr.append("**\n\n")

	if game.startTime is not None:
		bldr.append(" **Game Start Time:** ")
		bldr.append(unescapeMarkdown(game.startTime))
		bldr.append("\n\n")

	if game.location is not None:
		bldr.append(" **Location:** ")
		bldr.append(unescapeMarkdown(game.location))
		bldr.append("\n\n")

	if game.station is not None:
		bldr.append(" **Watch:** ")
		bldr.append(unescapeMarkdown(game.station))
		bldr.append("\n\n")


def renderOffenseType(offense):
	if offense == OffenseType.SPREAD:
		return "Spread"
	elif offense == OffenseType.PRO:
		return "Pro"
	elif offense == OffenseType.FLEXBONE:
		return "Flexbone"
	elif offense == OffenseType.AIR:
		return "Air"
	elif offense == OffenseType.PISTOL:
		return "Pistol"
	else:
		log.warning(f"Unknown offense type: {offense}")
		return offense.name


def renderDefenseType(defense):
	if defense == DefenseType.THREE_FOUR:
		return "3-4"
	elif defense == DefenseType.FOUR_THREE:
		return "4-3"
	elif defense == DefenseType.FIVE_TWO:
		return "5-2"
	elif defense == DefenseType.FOUR_FOUR:
		return "4-4"
	elif defense == DefenseType.THREE_THREE_FIVE:
		return "3-3-5"
	else:
		log.warning(f"Unknown defense type: {defense}")
		return defense.name


def renderTeamInfo(game, bldr):
	bldr.append("Team|Coach(es)|Offense|Defense\n")
	bldr.append(":-:|:-:|:-:|:-:\n")
	for homeAway in [False, True]:
		bldr.append(flair(game.team(homeAway)))
		bldr.append(" ")
		bldr.append(game.team(homeAway).name)
		bldr.append("|")
		bldr.append(getCoachString(game, homeAway))
		bldr.append("|")
		bldr.append(renderOffenseType(game.team(homeAway).playbook.offense))
		bldr.append("|")
		bldr.append(renderDefenseType(game.team(homeAway).playbook.defense))
		bldr.append("\n")


def renderTeamStats(game, bldr, homeAway):
	bldr.append(flair(game.team(homeAway)))
	bldr.append(" ")
	bldr.append(game.team(homeAway).name)
	bldr.append("\n\n")
	bldr.append(
		"Total Passing Yards|Total Rushing Yards|Total Yards|Interceptions Lost|Fumbles Lost|Field Goals|Time of Possession|Timeouts\n")
	bldr.append(":-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:\n")
	bldr.append("{} yards|{} yards|{} yards|{}|{}|{}/{}|{}|{}".format(
		game.status.stats(homeAway).yardsPassing,
		game.status.stats(homeAway).yardsRushing,
		game.status.stats(homeAway).yardsTotal,
		game.status.stats(homeAway).turnoverInterceptions,
		game.status.stats(homeAway).turnoverFumble,
		game.status.stats(homeAway).fieldGoalsScored,
		game.status.stats(homeAway).fieldGoalsAttempted,
		renderTime(game.status.stats(homeAway).posTime),
		game.status.state(homeAway).timeouts
	)
	)
	bldr.append("\n\n___\n")


def renderDrives(game, bldr):
	if len(game.status.drives):
		bldr.append("|Drive Summary|\n")
		bldr.append("|:-:|\n")
		for drive in game.status.drives:
			bldr.append("|[")
			bldr.append(str(drive['summary']))
			bldr.append("]")
			bldr.append("(")
			bldr.append(drive['url'])
			bldr.append(")|\n")
		bldr.append("\n")


def renderGameStatus(game, bldr):
	bldr.append("Clock|Quarter|Down|Ball Location|Possession|Playclock|Deadline\n")
	bldr.append(":-:|:-:|:-:|:-:|:-:|:-:|:-:\n")
	bldr.append(renderTime(game.status.clock))
	bldr.append("|")
	bldr.append(str(game.status.quarter))
	bldr.append("|")
	bldr.append(getDownString(game.status.down))
	bldr.append(" & ")
	bldr.append(str(game.status.yards))
	bldr.append("|")
	bldr.append(renderBallLocation(game, True))
	bldr.append("|")
	bldr.append(flair(game.team(game.status.possession)))
	bldr.append("|")
	bldr.append(renderDatetime(game.playclock))
	bldr.append("|")
	bldr.append(renderDatetime(game.deadline))
	bldr.append("\n\n")


def renderScore(game, bldr):
	bldr.append("Team|")
	numQuarters = max(len(game.status.homeState.quarters), len(game.status.awayState.quarters))
	for i in range(numQuarters):
		bldr.append("Q")
		bldr.append(str(i + 1))
		bldr.append("|")
	bldr.append("Total\n")
	bldr.append((":-:|" * (numQuarters + 2))[:-1])
	bldr.append("\n")
	for homeAway in [True, False]:
		bldr.append(flair(game.team(homeAway)))
		bldr.append("|")
		for quarter in game.status.state(homeAway).quarters:
			bldr.append(str(quarter))
			bldr.append("|")
		bldr.append("**")
		bldr.append(str(game.status.state(homeAway).points))
		bldr.append("**\n")


def renderGame(game):
	bldr = []

	renderGameInfo(game, bldr)
	bldr.append("\n\n")

	renderTeamInfo(game, bldr)
	bldr.append("___\n\n")

	for homeAway in [False, True]:
		renderTeamStats(game, bldr, homeAway)

	renderDrives(game, bldr)
	bldr.append("___\n\n")
	renderGameStatus(game, bldr)
	bldr.append("___\n\n")
	renderScore(game, bldr)

	bldr.append("\n\n")

	if game.playGist is not None:
		bldr.append("[Plays](")
		bldr.append(static.GIST_BASE_URL)
		bldr.append(static.GIST_USERNAME)
		bldr.append("/")
		bldr.append(game.playGist)
		bldr.append(")\n")
	else:
		bldr.append("Unable to generate play list\n")

	if game.forceChew:
		bldr.append("\n#This game is in default chew the clock mode.\n")

	if game.status.waitingId != "":
		bldr.append("\nWaiting on a response from {} to this {}.\n"
					.format(
						getCoachString(game, game.status.waitingOn),
						getLinkFromGameThing(game.thread, utils.getPrimaryWaitingId(game.status.waitingId))))

	if game.status.quarterType == QuarterType.END:
		bldr.append("\n#Game complete, {} wins!\n".format(game.status.winner))

	bldr.append("\n___\n\n")
	bldr.append("^Admin: ")
	bldr.append("[^Restart](")
	bldr.append(buildMessageLink(
		static.ACCOUNT_NAME,
		"Restart",
		f"restart {game.thread} Replace this with the reason you need to restart the game")
	)
	bldr.append(")")
	for homeAway in [False, True]:
		team = game.team(homeAway)

		bldr.append(" ^| [^Edit ^")
		bldr.append(team.name.replace(" ", " ^"))
		bldr.append("](")
		bldr.append(buildMessageLink(
			static.ACCOUNT_NAME,
			"teams",
			f"{team.tag}|{team.name}|{renderOffenseType(team.playbook.offense)}"
			f"|{renderDefenseType(team.playbook.defense)}"
			f"|{','.join(team.coaches)}"
			f"{('|'+team.conference) if team.conference is not None else ''}")
		)
		bldr.append(")")
	bldr.append(" ^| [^Rerun ^play](")
	bldr.append(buildMessageLink(
		static.ACCOUNT_NAME,
		"Rerun",
		f"rerun {game.thread}")
	)
	bldr.append(")")
	bldr.append(" ^| [^Pause](")
	bldr.append(buildMessageLink(
		static.ACCOUNT_NAME,
		"Pause",
		f"pause {game.thread} 12")
	)
	bldr.append(")")
	bldr.append(" ^| [^Abandon](")
	bldr.append(buildMessageLink(
		static.ACCOUNT_NAME,
		"Abandon ",
		f"abandon {game.thread}")
	)
	bldr.append(")")

	return ''.join(bldr)


def renderPlays(game):
	playBldr = [
		"Home score|Away score|Quarter|Clock|Ball Location|Possession|Down|Yards to go|Defensive number|"
		"Offensive number|Defensive submitter|Offensive submitter|Play|Result|Actual result|Yards|Play time|"
		"Runoff time"
	]
	for drive in game.status.plays:
		for play in drive:
			playBldr.append(str(play))
		playBldr.append("-"*80)

	return '\n'.join(playBldr)


def renderPostGame(game):
	bldr = []

	renderGameInfo(game, bldr)
	bldr.append("\n\n")

	for homeAway in [False, True]:
		renderTeamStats(game, bldr, homeAway)

	renderDrives(game, bldr)
	bldr.append("___\n\n")
	renderScore(game, bldr)

	bldr.append("\n\n")
	bldr.append("[Game thread](")
	bldr.append(static.SUBREDDIT_LINK)
	bldr.append(game.thread)
	bldr.append(")\n\n")

	if game.playGist is not None:
		bldr.append("[Plays](")
		bldr.append(static.GIST_BASE_URL)
		bldr.append(static.GIST_USERNAME)
		bldr.append("/")
		bldr.append(game.playGist)
		bldr.append(")\n")
	else:
		bldr.append("Unable to generate play list\n")

	bldr.append("\n")
	bldr.append("#Game complete, {} wins!".format(game.status.winner))

	return ''.join(bldr)


def getLinkFromGameThing(threadId, thingId):
	if thingId.startswith("t1"):
		waitingMessageType = "comment"
		link = "{}/_/{}".format(getLinkToThread(threadId), thingId[3:])
	elif thingId.startswith("t4"):
		waitingMessageType = "message"
		link = "{}{}".format(static.MESSAGE_LINK, thingId[3:])
	else:
		return "Something went wrong. Not valid thingid: {}".format(thingId)

	return "[{}]({})".format(waitingMessageType, link)


def getCoachString(game, isHome):
	bldr = []
	for coach in game.team(isHome).coaches:
		bldr.append("/u/{}".format(coach))
	return " and ".join(bldr)


def renderCoaches(coaches):
	bldr = []
	for coach in coaches:
		bldr.append("/u/{}".format(coach))
	return ", ".join(bldr)


def getNthQuarter(number):
	if number == 1:
		return "1st"
	elif number == 2:
		return "2nd"
	elif number == 3:
		return "3rd"
	elif number == 4:
		return "4th"
	elif number == 5:
		return "overtime"
	elif number == 6:
		return "2nd overtime"
	elif number == 7:
		return "3rd overtime"
	else:
		return "{}th overtime".format(number - 4)


def getNthWord(number):
	if number == 1:
		return "1st"
	elif number == 2:
		return "2nd"
	elif number == 3:
		return "3rd"
	elif number == 4:
		return "4th"
	else:
		return "{}th".format(number)


def getDownString(down):
	if down >= 1 and down <= 4:
		return getNthWord(down)
	else:
		log.warning("Hit a bad down number: {}".format(down))
		return "{}".format(down)


def getLocationString(game):
	location = game.status.location
	offenseTeam = game.team(game.status.possession).name
	defenseTeam = game.team(game.status.possession.negate()).name
	if location <= 0 or location >= 100:
		log.warning("Bad location: {}".format(location))
		return str(location)

	if location == 0:
		return "{} goal line".format(offenseTeam)
	if location < 50:
		return "{} {}".format(offenseTeam, location)
	elif location == 50:
		return str(location)
	else:
		return "{} {}".format(defenseTeam, 100 - location)


def getCurrentPlayString(game):
	bldr = []
	if game.status.waitingAction == Action.CONVERSION:
		bldr.append("{} just scored. ".format(game.team(game.status.possession).name))
	elif game.status.waitingAction == Action.KICKOFF:
		bldr.append("{} is kicking off. ".format(game.team(game.status.possession).name))
	else:
		bldr.append("It's {} and {} on the {}. ".format(
			getDownString(game.status.down),
			"goal" if game.status.location + game.status.yards >= 100 else game.status.yards,
			getLocationString(game)
		))

	if utils.isGameOvertime(game):
		if game.status.quarter == 5:
			bldr.append("In overtime.")
		else:
			bldr.append("In the {}.".format(getNthQuarter(game.status.quarter)))
	else:
		bldr.append("{} left in the {}.".format(renderTime(game.status.clock), getNthQuarter(game.status.quarter)))

	return ''.join(bldr)


def getWaitingOnString(game):
	string = "Error, no action"
	if game.status.waitingAction == Action.COIN:
		string = "Waiting on {} for coin toss".format(game.team(game.status.waitingOn).name)
	elif game.status.waitingAction == Action.DEFER:
		string = "Waiting on {} for receive/defer".format(game.team(game.status.waitingOn).name)
	elif game.status.waitingAction == Action.KICKOFF:
		string = "Waiting on {} for kickoff number".format(game.team(game.status.waitingOn).name)
	elif game.status.waitingAction == Action.PLAY:
		if game.status.waitingOn == game.status.possession:
			string = "Waiting on {} for an offensive play".format(game.team(game.status.waitingOn).name)
		else:
			string = "Waiting on {} for a defensive number".format(game.team(game.status.waitingOn).name)

	return string


def listSuggestedPlays(game):
	if game.status.waitingAction == Action.CONVERSION:
		if game.status.quarter >= 7:
			return "**two point**"
		else:
			return "**PAT** or **two point**"
	elif game.status.waitingAction == Action.KICKOFF:
		return "**normal**, **squib** or **onside**"
	else:
		if game.status.down == 4:
			if game.status.location > 62:
				return "**field goal**, or go for it with **run** or **pass**"
			elif game.status.location > 57:
				return "**punt** or **field goal**, or go for it with **run** or **pass**"
			else:
				return "**punt**, or go for it with **run** or **pass**"
		else:
			return "**run** or **pass**"


def htmlEncode(message):
	return urllib.parse.quote(message, safe='')


def buildMessageLink(recipient, subject, content=None):
	base = "https://np.reddit.com/message/compose/?"
	bldr = []
	bldr.append(f"to={recipient}")
	bldr.append(f"subject={htmlEncode(subject)}")
	if content is not None:
		bldr.append(f"message={htmlEncode(content)}")

	return base + '&'.join(bldr)


def renderDatetime(dtTm, includeLink=True):
	localized = pytz.utc.localize(dtTm).astimezone(static.EASTERN)
	timeString = localized.strftime("%m/%d %I:%M %p EST")
	if not includeLink:
		return timeString
	base = "https://www.timeanddate.com/countdown/afootball?p0=0&msg=Playclock&iso="
	return "[{}]({}{})".format(timeString, base, dtTm.strftime("%Y%m%dT%H%M%S"))


def renderGameStatusMessage(game):
	bldr = []
	bldr.append("[Game](")
	bldr.append(static.SUBREDDIT_LINK)
	bldr.append(game.thread)
	bldr.append(") status.\n\n")

	bldr.append(getCoachString(game, False))
	bldr.append(" as ")
	bldr.append(game.team(False).name)
	bldr.append("/away")
	bldr.append(" vs ")
	bldr.append(getCoachString(game, True))
	bldr.append(" as ")
	bldr.append(game.team(True).name)
	bldr.append("/home")
	bldr.append("\n\n")

	bldr.append("Status|Waiting|Link\n")
	bldr.append(":-:|:-:|:-:\n")

	for i, status in enumerate(game.previousStatus):
		bldr.append(game.team(status.possession).name)
		bldr.append("/")
		bldr.append(status.possession.name())
		bldr.append(" with ")
		bldr.append(getNthWord(status.down))
		bldr.append(" & ")
		bldr.append(str(status.yards))
		bldr.append(" on the ")
		bldr.append(str(status.location))
		bldr.append(" with ")
		bldr.append(renderTime(status.clock))
		bldr.append(" in ")
		if game.status.quarter != 5:
			bldr.append(" the ")
		bldr.append(getNthQuarter(status.quarter))
		bldr.append("|")
		primaryWaitingId = utils.getPrimaryWaitingId(status.waitingId)
		bldr.append(getLinkFromGameThing(game.thread, primaryWaitingId))
		bldr.append(" ")
		bldr.append(status.waitingOn.name())
		bldr.append("/")
		bldr.append(game.team(status.waitingOn).name)
		bldr.append(" for ")
		bldr.append(status.waitingAction.name)
		bldr.append("|")
		bldr.append("[Message](")
		bldr.append(buildMessageLink(
			static.ACCOUNT_NAME,
			"Kick game",
			"kick {} revert:{} message:{}".format(game.thread, i, status.messageId)
		))
		bldr.append(")\n")

	return ''.join(bldr)


def renderTeamsWiki(teams):
	conferences = defaultdict(list)
	for team in teams:
		conferences[teams[team].conference].append(teams[team])

	conferenceNames = []
	for conference in conferences:
		conferenceNames.append(conference)
		conferences[conference].sort(key=lambda team: team.tag)

	conferenceNames.sort(key=lambda name: name if name is not None else "")

	bldr = []
	for conference in conferenceNames:
		if conference is not None:
			bldr.append("***\n\n**")
			bldr.append(conference)
			bldr.append("**\n\n")

		bldr.append("Tag|Name|Offense|Defense|Coaches|CSS Tag|Current Game\\Plays|Edit\n")
		bldr.append(":-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:\n")

		for team in conferences[conference]:
			teamLine = f"{team.tag}|{team.name}|{renderOffenseType(team.playbook.offense)}|{renderDefenseType(team.playbook.defense)}"
			bldr.append(teamLine)
			bldr.append("|")
			bldr.append(renderCoaches(team.coaches))
			bldr.append("|")
			if team.css_tag is not None:
				bldr.append(team.css_tag)
			bldr.append("|")
			game = index.getGameFromTeamTag(team.tag)
			if game is not None:
				bldr.append("[Game](")
				bldr.append(static.SUBREDDIT_LINK)
				bldr.append(game.thread)
				bldr.append(")")
				if game.playGist is not None:
					bldr.append(" [Plays](")
					bldr.append(static.GIST_BASE_URL)
					bldr.append(static.GIST_USERNAME)
					bldr.append("/")
					bldr.append(game.playGist)
					bldr.append(")")
			bldr.append("|")
			bldr.append("[Edit](")
			bldr.append(buildMessageLink(
				static.ACCOUNT_NAME,
				"teams",
				f"{teamLine}"
				f"|{','.join(team.coaches)}"
				f"|{team.conference if team.conference is not None else ''}"
				f"|{team.css_tag if team.css_tag is not None else ''}")
			)
			bldr.append(")")
			bldr.append("\n")

	return ''.join(bldr)


def renderCoachesWiki(coaches):
	bldr = []

	bldr.append("Coach|Latest Response|Minutes Lag\n")
	bldr.append(":-:|:-:|:-:\n")

	min_count = 20
	for coach in coaches:
		bldr.append("u/")
		bldr.append(coach['username'])
		bldr.append("|")
		bldr.append(datetime.strptime(coach['latest'], "%Y-%m-%d %H:%M:%S").strftime("%m/%d"))
		bldr.append("|")
		if coach['count'] < min_count:
			bldr.append("NA: ")
			bldr.append(str(coach['count']))
			bldr.append("/")
			bldr.append(str(min_count))
		else:
			bldr.append(str(round(coach['seconds'] / 60, 2)))
		bldr.append("\n")

	return ''.join(bldr)
