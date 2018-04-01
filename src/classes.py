from datetime import datetime
from datetime import timedelta

import globals


class T:
	home = True
	away = False


class HomeAway:
	isHome = None

	def __init__(self, isHome):
		self.isHome = isHome

	def set(self, isHome):
		self.isHome = isHome

	def name(self):
		if self.isHome:
			return 'home'
		else:
			return 'away'

	def negate(self):
		return HomeAway(not self.isHome)

	def reverse(self):
		self.isHome = not self.isHome

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
	requestedTimeout = 'none'


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
	quarterType = 'normal'

	overtimePossession = None
	receivingNext = HomeAway(T.home)

	homeState = TeamState()
	awayState = TeamState()

	homeStats = TeamStats()
	awayStats = TeamStats()

	waitingId = None
	waitingAction = 'coin'
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
