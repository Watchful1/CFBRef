from datetime import datetime
from datetime import timedelta
from enum import Enum

import globals


class OffenseType(Enum):
	SPREAD = 1
	PRO = 2
	OPTION = 3


class DefenseType(Enum):
	THREE_FOUR = 1
	FOUR_THREE = 2
	FIVE_TWO = 3


class TimeoutOption(Enum):
	NONE = 1
	REQUESTED = 2
	USED = 3


class QuarterType(Enum):
	NORMAL = 1
	OVERTIME_NORMAL = 2
	OVERTIME_TIME = 3
	END = 3


class TimeOption(Enum):
	NONE = 1
	CHEW = 2
	HURRY = 3


class Action(Enum):
	COIN = 1
	DEFER = 2
	PLAY = 3
	CONVERSION = 4
	KICKOFF = 5
	OVERTIME = 6
	END = 6


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
	ERROR = 16


class T:
	home = True
	away = False


class PlaySummary:
	play = None
	result = None
	yards = None
	down = None
	toGo = None
	location = None
	time = None
	offNum = None
	defNum = None
	posHome = None


class HomeAway:
	isHome = None

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
		self.isHome = not self.isHome

	def copy(self):
		return HomeAway(self.isHome)

	def __eq__(self, value):
		if isinstance(value, bool):
			return self.isHome == value
		elif isinstance(value, str):
			return self.name() == value
		else:
			return NotImplemented

	def __bool__(self):
		return self.isHome

	def __str__(self):
		return self.name()


class TeamState:
	points = 0
	quarters = [0, 0, 0, 0]

	playclockPenalties = 0
	timeouts = 3
	requestedTimeout = TimeoutOption.NONE


class TeamStats:
	yardsPassing = 0
	yardsRushing = 0
	yardsTotal = 0
	turnoverInterceptions = 0
	turnoverFumble = 0
	fieldGoalsScored = 0
	fieldGoalsAttempted = 0
	posTime = 0


class GameStatus:
	clock = globals.quarterLength
	quarter = 1
	location = -1
	possession = HomeAway(T.home)
	down = 1
	yards = 10
	quarterType = QuarterType.NORMAL

	overtimePossession = None
	receivingNext = HomeAway(T.home)

	homeState = TeamState()
	awayState = TeamState()

	homeStats = TeamStats()
	awayStats = TeamStats()

	waitingId = None
	waitingAction = Action.COIN
	waitingOn = HomeAway(T.away)

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


class Team:
	tag = None
	name = None
	offense = None
	defense = None
	coaches = []
	record = None

	def __init__(self, tag, name, offense, defense):
		self.tag = tag
		self.name = name
		self.offense = offense
		self.defense = defense


class Game:
	home = None
	away = None
	dirty = False
	errored = False
	dataID = -1
	thread = "empty"

	status = GameStatus()
	previousStatus = []

	plays = []

	startTime = None
	location = None
	station = None
	playclock = datetime.utcnow() + timedelta(hours=24)
	deadline = datetime.utcnow() + timedelta(days=10)

	def __init__(self, home, away):
		self.home = home
		self.away = away

	def team(self, isHome):
		if isHome:
			return self.home
		else:
			return self.away
