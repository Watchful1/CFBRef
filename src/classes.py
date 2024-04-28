import logging
from datetime import datetime
from datetime import timedelta
from enum import Enum

import static

log = logging.getLogger("bot")


class Queue:
	def __init__(self, max_size):
		self.list = []
		self.hashset = set()
		self.max_size = max_size

	def put(self, item):
		# log.debug(f"Queue list: {str(self.list)}")
		# log.debug(f"Queue set: {str(self.hashset)}")
		if len(self.list) >= self.max_size:
			old_item = self.list.pop(0)
			if old_item in self.hashset:
				self.hashset.remove(old_item)
			else:
				log.warning(f"Couldn't remove item from set: {old_item} : {len(self.list)} : {len(self.hashset)}")

		self.list.append(item)
		self.hashset.add(item)

	def peek(self):
		return self.list[0] if len(self.list) > 0 else None

	def contains(self, item):
		return item in self.hashset


class RunStatus(Enum):
	CONTINUE = 1
	CONTINUE_QUARTER = 2
	STOP_QUARTER = 3


class OffenseType(Enum):
	SPREAD = 1
	PRO = 2
	FLEXBONE = 3
	AIR = 4
	PISTOL = 5


class DefenseType(Enum):
	THREE_FOUR = 1
	FOUR_THREE = 2
	FIVE_TWO = 3
	FOUR_FOUR = 4
	THREE_THREE_FIVE = 5


class TimeoutOption(Enum):
	NONE = 1
	REQUESTED = 2
	USED = 3


class QuarterType(Enum):
	NORMAL = 1
	OVERTIME_NORMAL = 2
	OVERTIME_TIME = 3
	END = 4


class TimeOption(Enum):
	NORMAL = 1
	CHEW = 2
	HURRY = 3
	RUN = 4


class Action(Enum):
	COIN = 1
	DEFER = 2
	PLAY = 3
	CONVERSION = 4
	KICKOFF = 5
	OVERTIME = 6
	END = 7


class Play(Enum):
	RUN = 1
	PASS = 2
	PUNT = 3
	FIELD_GOAL = 4
	KNEEL = 5
	SPIKE = 6
	PAT = 7
	TWO_POINT = 8
	KICKOFF_NORMAL = 9
	KICKOFF_SQUIB = 10
	KICKOFF_ONSIDE = 11
	DELAY_OF_GAME = 12


class PlayclockWarning(Enum):
	NONE = 1
	SIX_HOUR = 2
	TWELVE_HOUR = 3


class Result(Enum):
	GAIN = 1
	TURNOVER = 2
	TOUCHDOWN = 3
	TURNOVER_TOUCHDOWN = 4
	INCOMPLETE = 5
	TOUCHBACK = 6
	FIELD_GOAL = 7
	MISS = 8
	PAT = 9
	TWO_POINT = 10
	KICKOFF = 11
	PUNT = 12
	KICK = 13
	SPIKE = 14
	KNEEL = 15
	SAFETY = 16
	ERROR = 17
	TURNOVER_PAT = 18
	END_HALF = 19
	DELAY_OF_GAME = 20


class T:
	home = True
	away = False


class DriveSummary:
	def __init__(self):
		self.result = None
		self.yards = 0
		self.time = 0
		self.posHome = None

	def __str__(self):
		return "{} for {} yards in {} seconds ending in {}".format(
			"home" if self.posHome else "away",
			self.yards,
			self.time,
			self.result.name.lower()
		)


class PlaySummary:
	def __init__(self, game):
		self.homeScore = game.status.homeState.points
		self.awayScore = game.status.awayState.points
		self.quarter = game.status.quarter
		self.clock = game.status.clock
		self.location = game.status.location
		self.posHome = game.status.possession.copy()
		self.down = game.status.down
		self.toGo = game.status.yards
		self.offNum = None
		self.defNum = None
		self.defSubmitter = None
		self.offSubmitter = None
		self.play = None
		self.result = None
		self.actualResult = None
		self.yards = None
		self.playTime = None
		self.runoffTime = None

	def __str__(self):
		return "|".join([
			str(self.homeScore) if self.homeScore is not None else "",
			str(self.awayScore) if self.awayScore is not None else "",
			str(self.quarter) if self.quarter is not None else "",
			str(self.clock) if self.clock is not None else "",
			str(self.location) if self.location is not None else "",
			"home" if self.posHome else "away",
			str(self.down) if self.down is not None else "",
			str(self.toGo) if self.toGo is not None else "",
			str(self.defNum) if self.defNum is not None else "",
			str(self.offNum) if self.offNum is not None else "",
			self.defSubmitter if self.defSubmitter is not None else "",
			self.offSubmitter if self.offSubmitter is not None else "",
			self.play.name if self.play is not None else "",
			self.result.name if self.result is not None else "",
			self.actualResult.name if self.actualResult is not None else "",
			str(self.yards) if self.yards is not None else "",
			str(self.playTime) if self.playTime is not None else "",
			str(self.runoffTime) if self.runoffTime is not None else ""
		])


class HomeAway:
	def __init__(self, isHome):
		self.isHome = isHome

	def set(self, isHome):
		self.isHome = isHome

	def name(self):
		if self.isHome:
			return "home"
		else:
			return "away"

	def negate(self):
		return HomeAway(not self.isHome)

	def reverse(self):
		current = self.isHome
		reversed = not current
		self.isHome = reversed

	def copy(self):
		return HomeAway(self.isHome)

	def __eq__(self, value):
		if isinstance(value, bool):
			return self.isHome == value
		elif isinstance(value, str):
			return self.name() == value
		elif isinstance(value, HomeAway):
			return self.isHome == value.isHome
		else:
			return NotImplemented

	def __bool__(self):
		return self.isHome

	def __str__(self):
		return self.name()


class TeamState:
	def __init__(self):
		self.points = 0
		self.quarters = [0, 0, 0, 0]

		self.playclockPenalties = 0
		self.timeouts = 3
		self.requestedTimeout = TimeoutOption.NONE


class TeamStats:
	def __init__(self):
		self.yardsPassing = 0
		self.yardsRushing = 0
		self.yardsTotal = 0
		self.turnoverInterceptions = 0
		self.turnoverFumble = 0
		self.fieldGoalsScored = 0
		self.fieldGoalsAttempted = 0
		self.posTime = 0


class Playbook:
	def __init__(self, offense=None, defence=None):
		self.offense = offense
		self.defense = defence


class GameStatus:
	def __init__(self, quarterLength, quarter=1):
		self.clock = quarterLength
		self.quarter = quarter
		self.location = -1
		self.possession = HomeAway(T.home)
		self.down = 1
		self.yards = 10
		self.quarterType = QuarterType.NORMAL
		self.overtimePossession = None
		self.receivingNext = HomeAway(T.home)
		self.homeState = TeamState()
		self.awayState = TeamState()
		self.homeStats = TeamStats()
		self.awayStats = TeamStats()
		self.waitingId = ""
		self.waitingAction = Action.COIN
		self.waitingOn = HomeAway(T.away)
		self.defensiveNumber = None
		self.defensiveSubmitter = None
		self.messageId = None
		self.winner = None
		self.timeRunoff = False
		self.plays = [[]]
		self.drives = []
		self.noOnside = False
		self.timeoutMessages = []

		self.homePlaybook = Playbook()
		self.awayPlaybook = Playbook()

	def state(self, isHome):
		if isHome:
			return self.homeState
		else:
			return self.awayState

	def stats(self, isHome):
		if isHome:
			return self.homeStats
		else:
			return self.awayStats

	def playbook(self, isHome):
		if isHome:
			return self.homePlaybook
		else:
			return self.awayPlaybook

	def reset_defensive(self):
		self.defensiveNumber = None
		self.defensiveSubmitter = None


class Team:
	def __init__(self, tag, name, offense, defense, conference=None, css_tag=None):
		self.tag = tag
		self.name = name
		self.playbook = Playbook(offense, defense)
		self.coaches = []
		self.pastCoaches = []
		self.record = None
		self.conference = conference
		self.css_tag = css_tag


class Game:
	def __init__(self, home, away, quarterLength=None, quarter=1):
		self.home = home
		self.away = away

		self.dirty = False
		self.errored = False
		self.thread = "empty"
		self.previousStatus = []
		self.startTime = None
		self.location = None
		self.station = None
		self.prefix = None
		self.suffix = None
		self.playclock = datetime.utcnow() + timedelta(hours=18)
		self.deadline = datetime.utcnow() + timedelta(days=10)
		self.forceChew = False
		self.playclockWarning = PlayclockWarning.NONE
		self.playGist = None
		self.playRerun = False
		self.gistUpdatePending = False
		if quarterLength is None:
			self.quarterLength = 7*60
		else:
			self.quarterLength = quarterLength
		self.status = GameStatus(self.quarterLength, quarter=quarter)

	def team(self, isHome):
		if isHome:
			return self.home
		else:
			return self.away

	def __str__(self):
		return self.__dict__


movementPlays = [Play.RUN, Play.PASS]
normalPlays = [Play.RUN, Play.PASS, Play.PUNT, Play.FIELD_GOAL]
timePlays = [Play.KNEEL, Play.SPIKE]
conversionPlays = [Play.PAT, Play.TWO_POINT]
kickoffPlays = [Play.KICKOFF_NORMAL, Play.KICKOFF_SQUIB, Play.KICKOFF_ONSIDE]
playActions = [Action.PLAY, Action.CONVERSION, Action.KICKOFF]

driveEnders = [Result.TURNOVER, Result.FIELD_GOAL, Result.PUNT, Result.MISS, Result.SAFETY]
scoringResults = [Result.TOUCHDOWN, Result.TURNOVER_TOUCHDOWN]
postTouchdownEnders = [Result.PAT, Result.TWO_POINT, Result.KICKOFF, Result.TURNOVER_PAT]
