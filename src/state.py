import logging.handlers
from datetime import datetime

import wiki
import utils
import classes
import static
import string_utils
import drive_graphic
from classes import T
from classes import HomeAway
from classes import PlaySummary
from classes import Play
from classes import QuarterType
from classes import Action
from classes import TimeoutOption
from classes import TimeOption
from classes import OffenseType
from classes import Result
from classes import RunStatus

log = logging.getLogger("bot")


def scoreForTeam(game, points, homeAway):
	oldScore = game.status.state(homeAway).points
	game.status.state(homeAway).points += points
	log.debug("Score for {} changed from {} to {}".format(homeAway.name(), oldScore, game.status.state(homeAway).points))
	if len(game.status.state(homeAway).quarters) < game.status.quarter:
		game.status.state(homeAway).quarters.append(0)
	if len(game.status.state(homeAway.negate()).quarters) < game.status.quarter:
		game.status.state(homeAway.negate()).quarters.append(0)
	game.status.state(homeAway).quarters[game.status.quarter - 1] += points


def setStateTouchback(game, homeAway, yards=25):
	log.debug("Setting state to touchback for: {}".format(homeAway))
	game.status.location = yards
	game.status.down = 1
	game.status.yards = 10
	game.status.possession = homeAway.copy()
	game.status.waitingAction = Action.PLAY
	game.status.waitingOn = homeAway.copy()


def setStateKickoff(game, homeAway, yards=35, noOnside=False):
	log.debug("Setting state to kickoff for: {}".format(homeAway))
	game.status.location = yards
	game.status.down = 1
	game.status.yards = 10
	game.status.timeRunoff = False
	game.status.possession = homeAway.copy()
	game.status.waitingAction = Action.KICKOFF
	game.status.waitingOn = homeAway.copy()
	game.status.noOnside = noOnside


def setStateOvertimeDrive(game, homeAway):
	log.debug("Setting state to overtime drive for: {}".format(homeAway))
	if game.status.overtimePossession is None:
		game.status.overtimePossession = 1

	setStateTouchback(game, homeAway)
	game.status.location = 75


def forceEightPointTouchdown(game, homeAway):
	log.debug("Forcing touchdown and two point for: {}".format(homeAway))
	scoreForTeam(game, 8, homeAway)


def scoreTouchdown(game, homeAway):
	log.debug("Scoring touchdown for: {}".format(homeAway))
	scoreForTeam(game, 6, homeAway)
	game.status.location = 97
	game.status.down = 1
	game.status.yards = 10
	game.status.possession = homeAway.copy()
	game.status.waitingAction = Action.CONVERSION
	game.status.waitingOn = homeAway.copy()


def scoreFieldGoal(game, homeAway):
	scoreForTeam(game, 3, homeAway)


def scoreTwoPoint(game, homeAway):
	scoreForTeam(game, 2, homeAway)


def scorePAT(game, homeAway):
	scoreForTeam(game, 1, homeAway)


def turnover(game):
	game.status.down = 1
	game.status.yards = 10
	game.status.possession.reverse()
	game.status.location = 100 - game.status.location
	game.status.waitingAction = Action.PLAY
	game.status.waitingOn.reverse()


def overtimeTurnover(game):
	log.debug("Running overtime turnover")
	if game.status.overtimePossession == 1:
		log.debug("End of first overtime possession, starting second")
		game.status.overtimePossession = 2
		setStateOvertimeDrive(game, game.status.possession.negate())
		return wiki.getStringFromKey("overtimeDriveEnd", {'team': string_utils.flair(game.team(game.status.possession))})
	elif game.status.overtimePossession == 2:
		if game.status.state(T.home).points == game.status.state(T.away).points:
			if game.status.quarterType == QuarterType.OVERTIME_TIME and game.status.quarter >= 6:
				log.debug("End of 6th quarter in a time forced overtime, flipping coin for victor")
				if utils.coinToss():
					log.debug("Home has won")
					victor = HomeAway(T.home)
				else:
					log.debug("Away has won")
					victor = HomeAway(T.away)

				output = utils.endGame(game, game.team(victor).name)
				return wiki.getStringFromKey("overtimeForcedGameEnd", {'team': string_utils.flair(game.team(victor))}) + "\n\n" + output
			else:
				log.debug("End of second overtime possession, still tied, starting new quarter")
				game.status.overtimePossession = 1
				game.status.quarter += 1
				for homeAway in [HomeAway(True), HomeAway(False)]:
					if len(game.status.state(homeAway).quarters) < game.status.quarter:
						game.status.state(homeAway).quarters.append(0)
				setStateOvertimeDrive(game, game.status.receivingNext)
				game.status.receivingNext.reverse()
				return wiki.getStringFromKey("overtimeTiedQuarterEnd", {'quarter': string_utils.getNthQuarter(game.status.quarter)})

		else:
			log.debug("End of game")
			if game.status.state(T.home).points > game.status.state(T.away).points:
				victor = HomeAway(T.home)
			else:
				victor = HomeAway(T.away)
			output = utils.endGame(game, game.team(victor).name)
			return wiki.getStringFromKey("overtimeGameEnd", {'team': string_utils.flair(game.team(victor))}) + "\n\n" + output

	else:
		log.warning("Something went wrong. Invalid overtime possession: {}".format(game.status.overtimePossession))


def scoreSafety(game, homeAway):
	scoreForTeam(game, 2, homeAway)
	setStateKickoff(game, homeAway.negate(), 20, True)


def getNumberDiffForGame(game, offenseNumber):
	defenseNumber = game.status.defensiveNumber
	if defenseNumber is None:
		log.warning("Something went wrong, couldn't get a defensive number for that game")
		return -1

	straightDiff = abs(offenseNumber - defenseNumber)
	aroundRightDiff = abs(abs(1500-offenseNumber) + defenseNumber)
	aroundLeftDiff = abs(offenseNumber + abs(1500-defenseNumber))

	difference = min([straightDiff, aroundRightDiff, aroundLeftDiff])

	numberMessage = "Offense: {}\n\nDefense: {}\n\nDifference: {}".format(offenseNumber, defenseNumber, difference)
	log.debug("Offense: {} Defense: {} Result: {}".format(offenseNumber, defenseNumber, difference))

	return difference, numberMessage, defenseNumber


def findNumberInRangeDict(number, dict):
	for key in dict:
		rangeStart, rangeEnd = utils.getRange(key)
		if rangeStart is None:
			log.warning("Could not extract range: {}".format(key))
			continue

		if rangeStart <= number <= rangeEnd:
			return dict[key]

	log.warning("Could not find number in dict")
	return None


def getPlayResult(game, play, number):
	playDict = wiki.getPlay(play)
	if playDict is None:
		log.warning(f"{play} is not a valid play")
		return None

	log.debug(f"Getting play result for: {play} : {100 - game.status.location}")
	if play in classes.movementPlays:
		offense = game.status.playbook(game.status.possession).offense
		defense = game.status.playbook(game.status.possession.negate()).defense
		log.debug("Movement play offense, defense: {} : {}".format(offense, defense))
		playMajorRange = playDict[offense][defense]
	else:
		playMajorRange = playDict

	playMinorRange = findNumberInRangeDict(100 - game.status.location, playMajorRange)
	result = findNumberInRangeDict(number, playMinorRange)
	log.debug(f"Result: {result['result']} : {result['yards'] if 'yards' in result else 'no yards'}")
	return result


def getTimeAfterForOffense(game, homeAway):
	offenseType = game.status.playbook(homeAway).offense
	if offenseType == OffenseType.SPREAD:
		return 10
	elif offenseType == OffenseType.PRO:
		return 15
	elif offenseType == OffenseType.OPTION:
		return 20
	else:
		log.warning("Not a valid offense: {}".format(offenseType))
		return None


def getTimeByPlay(play, result, yards):
	timePlay = wiki.getTimeByPlay(play)
	if timePlay is None:
		log.warning("Could not get time result for play: {}".format(play))
		return None

	if result not in timePlay:
		log.warning("Could not get result in timePlay: {} : {} : {}".format(play, result, timePlay))
		return None

	timeObject = timePlay[result]
	if result in [Result.GAIN, Result.KICK]:
		closestObject = None
		currentDifference = 100
		for yardObject in timeObject:
			difference = abs(yardObject['yards'] - yards)
			if difference < currentDifference:
				currentDifference = difference
				closestObject = yardObject

		if closestObject is None:
			log.warning("Could not get any yardObject")
			return None

		log.debug("Found a valid time object in gain, returning: {}".format(closestObject['time']))
		return closestObject['time']

	else:
		log.debug("Found a valid time object in {}, returning: {}".format(result, timeObject['time']))
		return timeObject['time']


def checkQuarterStatus(game, timeOffClock):
	if game.status.clock <= 0 and game.status.waitingAction not in [Action.CONVERSION]:
		log.debug("End of quarter: {}".format(game.status.quarter))
		timeOffClock = timeOffClock + game.status.clock
		if game.status.quarter == 1:
			timeMessage = "end of the first quarter"
			game.status.timeRunoff = False
			runStatus = RunStatus.CONTINUE_QUARTER
		elif game.status.quarter == 3:
			timeMessage = "end of the third quarter"
			game.status.timeRunoff = False
			runStatus = RunStatus.CONTINUE_QUARTER
		else:
			runStatus = RunStatus.STOP_QUARTER
			if game.status.quarter == 4:
				if game.status.state(T.home).points == game.status.state(T.away).points:
					log.debug("Score tied at end of 4th, going to overtime")
					timeMessage = "end of regulation. The score is tied, we're going to overtime!"
					if game.deadline < datetime.utcnow():
						log.debug(f"Game past deadline, {game.deadline}, {datetime.utcnow()}")
						game.status.quarterType = QuarterType.OVERTIME_TIME
					else:
						game.status.quarterType = QuarterType.OVERTIME_NORMAL
					game.status.waitingAction = Action.OVERTIME
				else:
					log.debug("End of game")
					if game.status.state(T.home).points > game.status.state(T.away).points:
						victor = HomeAway(T.home)
					else:
						victor = HomeAway(T.away)
					output = utils.endGame(game, game.team(victor).name)
					timeMessage = "end of the game! {} has won!\n\n{}".format(string_utils.flair(game.team(victor)), output)
				game.status.clock = 0
			else:
				if game.status.quarter == 2:
					log.debug("End of half")
					timeMessage = "end of the first half"
				else:
					log.debug("Wrong quarter: {}".format(game.status.quarter))
					timeMessage = "something went wrong"

				setStateKickoff(game, game.status.receivingNext.negate())
				game.status.receivingNext.reverse()
				game.status.state(T.home).timeouts = 3
				game.status.state(T.away).timeouts = 3

		if game.status.quarterType != QuarterType.END:
			game.status.quarter += 1
			game.status.clock = static.quarterLength

	else:
		timeMessage = None
		runStatus = RunStatus.CONTINUE

	log.debug("Actual time off: {} : {}".format(timeOffClock, runStatus))
	return runStatus, timeOffClock, timeMessage


def betweenPlayRunoff(game, play, offenseHomeAway, timeOption):
	timeOffClock = 0
	if game.status.timeRunoff:
		if game.status.state(offenseHomeAway).requestedTimeout == TimeoutOption.REQUESTED:
			log.debug("Using offensive timeout")
			game.status.state(offenseHomeAway).requestedTimeout = TimeoutOption.USED
			game.status.state(offenseHomeAway).timeouts -= 1
		elif game.status.state(offenseHomeAway.negate()).requestedTimeout == TimeoutOption.REQUESTED:
			log.debug("Using defensive timeout")
			game.status.state(offenseHomeAway.negate()).requestedTimeout = TimeoutOption.USED
			game.status.state(offenseHomeAway.negate()).timeouts -= 1
		else:
			if timeOption == TimeOption.RUN:
				timeOffClock = min(max(game.status.clock - 1, 7), 31)
			elif play == Play.KNEEL:
				timeOffClock = 39
			elif play == Play.SPIKE:
				timeOffClock = 2
			elif timeOption == TimeOption.CHEW:
				timeOffClock = 30
			elif timeOption == TimeOption.HURRY:
				timeOffClock = 7
			else:
				timeOffClock = getTimeAfterForOffense(game, offenseHomeAway)

	log.debug("Between play runoff: {} : {} : {}".format(game.status.clock, timeOffClock, game.status.timeRunoff))

	game.status.clock -= timeOffClock
	game.status.timeRunoff = False

	runStatus, timeOffClock, timeMessage = checkQuarterStatus(game, timeOffClock)
	utils.addStat(game, 'posTime', timeOffClock, offenseHomeAway)

	if runStatus == RunStatus.CONTINUE_QUARTER:
		timeMessage = "That's the {}".format(timeMessage)
	elif runStatus == RunStatus.STOP_QUARTER:
		timeMessage = "The clock ran out before the play was run. That's the {}".format(timeMessage)

	return runStatus, timeMessage, timeOffClock


def updateTime(game, play, result, actualResult, yards, offenseHomeAway, timeOption, timeBetweenPlay, isConversion):
	log.debug("Updating time with: {} : {} : {} : {} : {} : {} : {}".format(play, result, actualResult, yards, offenseHomeAway, timeOption, isConversion))
	timeOffClock = 0

	if actualResult in [Result.TOUCHDOWN, Result.TOUCHBACK, Result.SAFETY] and play not in classes.kickoffPlays:
		timeResult = Result.GAIN
	elif result == Result.INCOMPLETE:
		timeResult = Result.INCOMPLETE
	elif actualResult == Result.TURNOVER and result == Result.GAIN:
		timeResult = Result.GAIN
	else:
		timeResult = actualResult

	game.status.timeRunoff = False
	if play == Play.SPIKE:
		timeOffClock += 1
	elif play == Play.PAT:
		timeOffClock += 0
	elif play == Play.TWO_POINT:
		timeOffClock += 0
	else:
		if play == Play.KNEEL:
			if not isConversion:
				timeOffClock += 1
		else:
			timeOffClock += getTimeByPlay(play, timeResult, yards)

		if actualResult in [Result.GAIN, Result.KNEEL] and result != Result.INCOMPLETE and play not in classes.kickoffPlays:
			game.status.timeRunoff = True

	log.debug("Time off clock: {} : {} : {}".format(game.status.clock, timeOffClock, game.status.timeRunoff))

	game.status.clock -= timeOffClock

	runStatus, timeOffClock, timeMessage = checkQuarterStatus(game, timeOffClock)
	if timeMessage is not None:
		timeMessage = "that's the " + timeMessage
	else:
		timeMessage = "{} left".format(string_utils.renderTime(game.status.clock))

	utils.addStat(game, 'posTime', timeOffClock, offenseHomeAway)

	return "The play took {} seconds, {}".format(max(timeOffClock + timeBetweenPlay, 0), timeMessage), timeOffClock


def executeGain(game, play, yards, incomplete=False):
	if play not in classes.movementPlays and play not in [Play.PUNT]:
		log.warning("This doesn't look like a valid movement play: {}".format(play))
		return Result.ERROR, None, "Something went wrong trying to move the ball"

	previousLocation = game.status.location
	log.debug("Ball moved from {} to {}".format(previousLocation, previousLocation + yards))
	game.status.location = previousLocation + yards
	if game.status.location >= 100:
		log.debug("Ball passed the line, touchdown offense")

		utils.addStatRunPass(game, play, 100 - previousLocation)
		scoreTouchdown(game, game.status.possession)

		if play == Play.RUN:
			resultMessage = wiki.getStringFromKey("runTouchdown", {'team': game.team(game.status.possession).name, 'yards': yards})
		elif play == Play.PASS:
			resultMessage = wiki.getStringFromKey("passTouchdown", {'team': game.team(game.status.possession).name, 'yards': yards})
		else:
			resultMessage = "It's a touchdown!"

		return Result.TOUCHDOWN, 100 - previousLocation, resultMessage
	elif game.status.location <= 0:
		log.debug("Ball went back over the line, safety for the defense")

		utils.addStatRunPass(game, play, previousLocation * -1)
		scoreSafety(game, game.status.possession.negate())

		if play == Play.RUN:
			resultMessage = wiki.getStringFromKey("runSafety")
		elif play == Play.PASS:
			resultMessage = wiki.getStringFromKey("passSafety")
		else:
			resultMessage = "It's a safety!"

		return Result.SAFETY, 0 - previousLocation, resultMessage
	else:
		log.debug("Ball moved, but didn't enter an endzone, checking and updating play status")

		utils.addStatRunPass(game, play, yards)
		yardsRemaining = game.status.yards - yards

		if yardsRemaining <= 0:
			log.debug("First down")
			game.status.yards = 10
			game.status.down = 1

			if play == Play.RUN:
				resultMessage = wiki.getStringFromKey("runFirstDown", {'yards': yards, 'team': game.team(game.status.possession).name, 'yardLine': string_utils.getLocationString(game)})
			elif play == Play.PASS:
				resultMessage = wiki.getStringFromKey("passFirstDown", {'yards': yards, 'team': game.team(game.status.possession).name, 'yardLine': string_utils.getLocationString(game)})
			else:
				resultMessage = "It's a first down"

			return Result.GAIN, game.status.location - previousLocation, resultMessage
		else:
			log.debug("Not a first down, incrementing down")
			game.status.down += 1
			if game.status.down > 4:
				log.debug("Turnover on downs")
				if incomplete:
					resultMessage = wiki.getStringFromKey("turnoverDownsIncomplete", {'team': game.team(game.status.possession).name})
				else:
					if play == Play.RUN:
						resultMessage = wiki.getStringFromKey("turnoverDownsRun", {'yards': yards})
					elif play == Play.PASS:
						resultMessage = wiki.getStringFromKey("turnoverDownsPass", {'yards': yards})
					else:
						resultMessage = "Turnover on downs"

				if utils.isGameOvertime(game):
					resultMessage = "{}\n\n{}".format(resultMessage, overtimeTurnover(game))
				else:
					turnover(game)
				return Result.TURNOVER, yards, resultMessage
			else:
				log.debug("Now {} down and {}".format(string_utils.getDownString(game.status.down), yardsRemaining))
				game.status.yards = yardsRemaining

				if incomplete:
					resultMessage = wiki.getStringFromKey("incompletePass", {'down': string_utils.getDownString(game.status.down), 'yardsLeft': yardsRemaining})
				else:
					statsTable = {
						'yards': yards,
						'negativeYards': yards * -1,
						'down': string_utils.getDownString(game.status.down),
						'yardsLeft': "goal" if game.status.location + yardsRemaining >= 100 else yardsRemaining,
						'team': game.team(game.status.possession).name,
						'yardLine': string_utils.getLocationString(game)
					}
					if play == Play.RUN:
						if yards < 0:
							resultMessage = wiki.getStringFromKey("gainRunNegative", statsTable)
						elif yards > 0:
							resultMessage = wiki.getStringFromKey("gainRunPositive", statsTable)
						else:
							resultMessage = wiki.getStringFromKey("gainRunZero", statsTable)
					elif play == Play.PASS:
						if yards < 0:
							resultMessage = wiki.getStringFromKey("gainPassNegative", statsTable)
						elif yards > 0:
							resultMessage = wiki.getStringFromKey("gainPassPositive", statsTable)
						else:
							resultMessage = wiki.getStringFromKey("gainPassZero", statsTable)
					else:
						resultMessage = "Yards gained"

				return Result.GAIN, game.status.location - previousLocation, resultMessage


def executePunt(game, yards):
	log.debug("Ball punted for {} yards".format(yards))
	game.status.location = game.status.location + yards
	if game.status.location >= 100:
		log.debug("Punted into the end zone, touchback")
		setStateTouchback(game, game.status.possession.negate(), 20)
		if game.status.location > 110:
			return wiki.getStringFromKey("puntOutOfEndZone")
		else:
			return wiki.getStringFromKey("puntInEndZone")
	else:
		log.debug("Punt caught, setting up turnover")
		if utils.isGameOvertime(game):
			return overtimeTurnover(game)
		else:
			turnover(game)
			return wiki.getStringFromKey("puntYards", {'yards': yards, 'yardLine': string_utils.getLocationString(game)})


def executePlay(game, play, number, timeOption, isConversion, offensive_submitter):
	startingPossessionHomeAway = game.status.possession.copy()
	actualResult = None
	result = None
	yards = None
	resultMessage = "Something went wrong, I should never have reached this"
	diffMessage = None
	success = True
	timeMessage = None

	playSummary = PlaySummary()
	playSummary.homeScore = game.status.homeState.points
	playSummary.awayScore = game.status.awayState.points
	playSummary.quarter = game.status.quarter
	playSummary.clock = game.status.clock
	playSummary.down = game.status.down
	playSummary.toGo = game.status.yards
	playSummary.location = game.status.location
	playSummary.offNum = number
	playSummary.posHome = game.status.possession.copy()
	playSummary.offSubmitter = offensive_submitter
	playSummary.defSubmitter = game.status.defensiveSubmitter

	runoffResult, timeMessageBetweenPlay, timeBetweenPlay = betweenPlayRunoff(game, play, startingPossessionHomeAway, timeOption)

	playSummary.runoffTime = timeBetweenPlay

	if runoffResult == RunStatus.STOP_QUARTER:
		log.debug("Hit stop_quarter, not running play")
	else:
		if isConversion:
			log.debug("Executing conversion play: {}".format(play))
			if play in classes.timePlays:
				if play == Play.KNEEL:
					log.debug("Running kneel play in conversion")
					actualResult = Result.KNEEL
					result = {'result': actualResult}

					resultMessage = wiki.getStringFromKey("kneel")
					if utils.isGameOvertime(game):
						timeMessage = overtimeTurnover(game)
					else:
						setStateKickoff(game, game.status.possession)

				elif play == Play.SPIKE:
					log.debug("Running spike play in conversion")
					actualResult = Result.SPIKE
					result = {'result': actualResult}

					resultMessage = wiki.getStringFromKey("spike")
					if utils.isGameOvertime(game):
						timeMessage = overtimeTurnover(game)
					else:
						setStateKickoff(game, game.status.possession)

			elif play in classes.conversionPlays:
				numberResult, diffMessage, defenseNumber = getNumberDiffForGame(game, number)
				playSummary.defNum = defenseNumber
				result = getPlayResult(game, play, numberResult)
				actualResult = result['result']

				if result['result'] == Result.TWO_POINT:
					log.debug("Successful two point conversion")
					resultMessage = wiki.getStringFromKey("scoredTwoPointConversion")
					scoreTwoPoint(game, game.status.possession)
					if utils.isGameOvertime(game):
						timeMessage = overtimeTurnover(game)
					else:
						setStateKickoff(game, game.status.possession)

				elif result['result'] == Result.PAT:
					log.debug("Successful PAT")
					resultMessage = wiki.getStringFromKey("scoredPAT")
					scorePAT(game, game.status.possession)
					if utils.isGameOvertime(game):
						timeMessage = overtimeTurnover(game)
					else:
						setStateKickoff(game, game.status.possession)

				elif result['result'] == Result.KICKOFF:
					log.debug("Attempt unsuccessful")
					if play == Play.TWO_POINT:
						resultMessage = wiki.getStringFromKey("failedTwoPointConversion")
					elif play == Play.PAT:
						resultMessage = wiki.getStringFromKey("failedPAT")
					else:
						resultMessage = wiki.getStringFromKey("failedConversion")
					if utils.isGameOvertime(game):
						timeMessage = overtimeTurnover(game)
					else:
						setStateKickoff(game, game.status.possession)

				elif result['result'] == Result.TURNOVER_PAT:
					log.debug("Turnover PAT")
					resultMessage = wiki.getStringFromKey("turnoverPAT", {'team': game.team(game.status.possession.negate()).name})
					scoreTwoPoint(game, game.status.possession.negate())
					if utils.isGameOvertime(game):
						timeMessage = overtimeTurnover(game)
					else:
						setStateKickoff(game, game.status.possession)

			else:
				log.warning(f"Bad conversion play: {play}")
				resultMessage = "Something went wrong, invalid play: {}".format(play)
				success = False

			game.status.reset_defensive()

		elif play in classes.kickoffPlays:
			numberResult, diffMessage, defenseNumber = getNumberDiffForGame(game, number)
			playSummary.defNum = defenseNumber

			log.debug("Executing kickoff play: {}".format(play))
			game.status.noOnside = False
			result = getPlayResult(game, play, numberResult)
			actualResult = result['result']

			if result['result'] == Result.KICK:
				if 'yards' not in result:
					log.warning("Result is a successful kick, but I couldn't find any yards")
					resultMessage = "Result of kick is a number of yards, but something went wrong and I couldn't find what number"
					success = False
				else:
					log.debug("Result is a kick of {} yards".format(result['yards']))
					yards = result['yards']
					game.status.location = game.status.location + yards
					if utils.isGameOvertime(game):
						timeMessage = overtimeTurnover(game)
					else:
						turnover(game)
					resultMessage = wiki.getStringFromKey("successfulKickoff", {'yards': yards, 'yardLine': string_utils.getLocationString(game)})

			elif result['result'] == Result.GAIN:
				if 'yards' not in result:
					log.warning("Result is a dropped kick, but I couldn't find any yards")
					resultMessage = "The receiver drops the kick, but something went wrong and I couldn't find where"
					success = False
				else:
					log.debug("Result is a dropped kick of {} yards".format(result['yards']))
					yards = result['yards']
					game.status.location = game.status.location + yards
					resultMessage = wiki.getStringFromKey("turnoverKickoff", {'team': game.team(game.status.possession).name, 'location': string_utils.getLocationString(game)})
					game.status.waitingAction = Action.PLAY

			elif result['result'] == Result.TOUCHBACK:
				log.debug("Result is a touchback")
				setStateTouchback(game, game.status.possession.negate())
				resultMessage = wiki.getStringFromKey("touchback")

			elif result['result'] == Result.TOUCHDOWN:
				log.debug("Result is a touchdown")
				resultMessage = wiki.getStringFromKey("touchdownKickoff", {'team': game.team(game.status.possession).name})
				scoreTouchdown(game, game.status.possession)

			elif result['result'] == Result.TURNOVER_TOUCHDOWN:
				log.debug("Result is a run back for touchdown")
				resultMessage = wiki.getStringFromKey("turnoverTouchdownKickoff", {'team': game.team(game.status.possession.negate()).name})
				scoreTouchdown(game, game.status.possession.negate())

		elif play in classes.normalPlays:
			numberResult, diffMessage, defenseNumber = getNumberDiffForGame(game, number)
			playSummary.defNum = defenseNumber

			log.debug("Executing normal play: {}".format(play))
			result = getPlayResult(game, play, numberResult)

			if play == Play.FIELD_GOAL:
				utils.addStat(game, 'fieldGoalsAttempted', 1)

			actualResult = result['result']
			if play == Play.PUNT and result['result'] == Result.GAIN and game.status.location + result['yards'] >= 100:
				result['yards'] = (100 - 4) - game.status.location

			if result['result'] == Result.GAIN:
				if play == Play.PUNT:
					log.debug("Muffed punt. Ball moved from {} to {}".format(game.status.location, game.status.location + result['yards']))
					game.status.location = game.status.location + result['yards']
					game.status.yards = 10
					game.status.down = 1
					yards = result['yards']
					resultMessage = wiki.getStringFromKey("turnoverPunt", {'team': game.team(game.status.possession).name, 'location': string_utils.getLocationString(game)})

				else:
					if 'yards' not in result:
						log.warning("Result is a gain, but I couldn't find any yards")
						resultMessage = "Result of play is a number of yards, but something went wrong and I couldn't find what number"
						success = False
					else:
						log.debug("Result is a gain of {} yards".format(result['yards']))
						gainResult, yards, resultMessage = executeGain(game, play, result['yards'])
						if gainResult != Result.ERROR:
							if yards is not None:
								actualResult = gainResult
						else:
							success = False

			elif result['result'] == Result.INCOMPLETE:
				log.debug("Result is an incomplete pass")
				actualResult, yards, resultMessage = executeGain(game, play, 0, True)

			elif result['result'] == Result.TOUCHDOWN:
				log.debug("Result is a touchdown")

				previousLocation = game.status.location
				utils.addStatRunPass(game, play, 100 - previousLocation)
				yards = 100 - previousLocation

				if play == Play.RUN:
					resultMessage = wiki.getStringFromKey("runTouchdown", {'team': game.team(game.status.possession).name, 'yards': yards})
				elif play == Play.PASS:
					resultMessage = wiki.getStringFromKey("passTouchdown", {'team': game.team(game.status.possession).name, 'yards': yards})
				else:
					resultMessage = "It's a touchdown!"

				scoreTouchdown(game, game.status.possession)

			elif result['result'] == Result.FIELD_GOAL:
				log.debug("Result is a field goal")
				resultMessage = wiki.getStringFromKey("successfulFieldGoal", {'yards': 100 - game.status.location + 17})
				utils.addStat(game, 'fieldGoalsScored', 1)
				scoreFieldGoal(game, game.status.possession)
				if utils.isGameOvertime(game):
					timeMessage = overtimeTurnover(game)
				else:
					setStateKickoff(game, game.status.possession)

			elif result['result'] == Result.PUNT:
				if 'yards' not in result:
					log.warning("Result is a punt, but I couldn't find any yards")
					resultMessage = "Result of play is a successful punt, but something went wrong and I couldn't find how long a punt"
				else:
					log.debug("Successful punt of {} yards".format(result['yards']))
					if utils.isGameOvertime(game):
						log.warning("A punt happened in overtime, this shouldn't have happened")
						resultMessage = "A punt happened, but it's overtime. This shouldn't be possible."
					else:
						resultMessage = executePunt(game, result['yards'])
						yards = result['yards']

			elif result['result'] in [Result.TURNOVER, Result.MISS, Result.TURNOVER_TOUCHDOWN]:
				if result['result'] == Result.TURNOVER and 'yards' in result:
					yards = result['yards']
					previousLocation = game.status.location
					log.debug("Ball turnover moved from {} to {}".format(previousLocation, previousLocation + yards))
					game.status.location = previousLocation + yards
					if game.status.location >= 100:
						log.debug("Ball recovered by defense in their own endzone, touchback")
						actualResult = Result.TOUCHBACK

					elif game.status.location <= 0:
						log.debug("Ball recovered by defense in their offenses endzone, touchdown")
						actualResult = Result.TURNOVER_TOUCHDOWN
				else:
					yards = 0

				if actualResult in [Result.TURNOVER, Result.MISS]:
					log.debug("Play results in a turnover")
					statsTable = {
						'team': game.team(game.status.possession.negate()).name,
						'yards': yards,
						'negativeYards': yards * -1
					}
					if play == Play.RUN:
						utils.addStat(game, 'turnoverFumble', 1)
						if yards < 0:
							resultMessage = wiki.getStringFromKey("turnoverFumbleNegative", statsTable)
						elif yards > 0:
							resultMessage = wiki.getStringFromKey("turnoverFumblePositive", statsTable)
						else:
							resultMessage = wiki.getStringFromKey("turnoverFumbleZero", statsTable)
					elif play == Play.PASS:
						utils.addStat(game, 'turnoverInterceptions', 1)
						if yards < 0:
							resultMessage = wiki.getStringFromKey("turnoverInterceptionNegative", statsTable)
						elif yards > 0:
							resultMessage = wiki.getStringFromKey("turnoverInterceptionPositive", statsTable)
						else:
							resultMessage = wiki.getStringFromKey("turnoverInterceptionZero", statsTable)
					elif play == Play.FIELD_GOAL:
						if result['result'] == Result.TURNOVER:
							utils.addStat(game, 'turnoverFumble', 1)
							resultMessage = wiki.getStringFromKey("blockedFieldGoal")
						else:
							resultMessage = wiki.getStringFromKey("missedFieldGoal")

					elif play == Play.PUNT:
						utils.addStat(game, 'turnoverFumble', 1)
						resultMessage = wiki.getStringFromKey("blockedPunt")
					else:
						utils.addStat(game, 'turnoverFumble', 1)
						resultMessage = "It's a turnover!"
					if utils.isGameOvertime(game):
						timeMessage = overtimeTurnover(game)
					else:
						turnover(game)

				elif actualResult == Result.TOUCHBACK:
					log.debug("Play results in a turnover in defenders endzone")
					if play == Play.RUN:
						utils.addStat(game, 'turnoverFumble', 1)
						resultMessage = wiki.getStringFromKey("turnoverFumbleTouchback", {'team': game.team(game.status.possession.negate()).name})
					elif play == Play.PASS:
						utils.addStat(game, 'turnoverInterceptions', 1)
						resultMessage = wiki.getStringFromKey("turnoverInterceptionTouchback", {'team': game.team(game.status.possession.negate()).name})
					else:
						utils.addStat(game, 'turnoverFumble', 1)
						resultMessage = "It's a turnover!"
					if utils.isGameOvertime(game):
						timeMessage = overtimeTurnover(game)
					else:
						setStateTouchback(game, game.status.possession.negate(), 20)

				elif actualResult == Result.TURNOVER_TOUCHDOWN:
					log.debug("Play results in a turnover and run back")
					if play == Play.RUN:
						utils.addStat(game, 'turnoverFumble', 1)
						resultMessage = wiki.getStringFromKey("turnoverTouchdownRun", {'team': game.team(game.status.possession.negate()).name})
					elif play == Play.PASS:
						utils.addStat(game, 'turnoverInterceptions', 1)
						resultMessage = wiki.getStringFromKey("turnoverTouchdownPass", {'team': game.team(game.status.possession.negate()).name})
					elif play == Play.FIELD_GOAL:
						resultMessage = wiki.getStringFromKey("turnoverTouchdownFieldGoal", {'team': game.team(game.status.possession.negate()).name})
					elif play == Play.PUNT:
						utils.addStat(game, 'turnoverFumble', 1)
						resultMessage = wiki.getStringFromKey("turnoverTouchdownPunt", {'team': game.team(game.status.possession.negate()).name})
					else:
						utils.addStat(game, 'turnoverFumble', 1)
						resultMessage = "It's a turnover and run back for a touchdown!"
					yards = game.status.location
					scoreTouchdown(game, game.status.possession.negate())
					if utils.isGameOvertime(game):
						output = utils.endGame(game, game.team(game.status.possession).name)
						timeMessage = "Game over! {} wins!\n\n{}".format(string_utils.flair(game.team(game.status.possession)), output)

			game.status.reset_defensive()

		elif play in classes.timePlays:
			if play == Play.KNEEL:
				log.debug("Running kneel play")
				actualResult = Result.KNEEL
				result = {'result': actualResult}
				game.status.down += 1

				newLocation = max(game.status.location - 2, 1)
				utils.addStatRunPass(game, Play.RUN, newLocation - game.status.location)
				log.debug("Kneel moved ball from {} to {}".format(game.status.location, newLocation))
				yards = newLocation - game.status.location
				game.status.location = newLocation
				game.status.yards = game.status.yards - yards

				if game.status.down > 4:
					log.debug("Turnover on downs")
					if utils.isGameOvertime(game):
						timeMessage = overtimeTurnover(game)
					else:
						turnover(game)
					actualResult = Result.TURNOVER
					resultMessage = wiki.getStringFromKey("turnoverDownsKneel")
				else:
					resultMessage = wiki.getStringFromKey("kneel")

			elif play == Play.SPIKE:
				log.debug("Running spike play")
				actualResult = Result.SPIKE
				result = {'result': actualResult}
				game.status.down += 1
				if game.status.down > 4:
					log.debug("Turnover on downs")
					if utils.isGameOvertime(game):
						timeMessage = overtimeTurnover(game)
					else:
						turnover(game)
					actualResult = Result.TURNOVER
					resultMessage = wiki.getStringFromKey("turnoverDownsSpike")
				else:
					resultMessage = wiki.getStringFromKey("spike")

			game.status.reset_defensive()

		else:
			log.debug("Something went wrong, invalid play: {}".format(play))
			resultMessage = "Something went wrong, invalid play: {}".format(play)
			success = False

	if runoffResult == RunStatus.STOP_QUARTER:
		messages = []
	else:
		messages = [resultMessage]
	timeOffClock = None
	if actualResult is not None and game.status.quarterType == QuarterType.NORMAL:
		if timeMessage is None:
			timeMessage, timeOffClock = updateTime(
				game,
				play,
				result['result'],
				actualResult,
				yards,
				startingPossessionHomeAway,
				timeOption,
				timeBetweenPlay,
				isConversion)

	if timeMessageBetweenPlay is not None:
		messages.append(timeMessageBetweenPlay)

	if timeMessage is not None:
		messages.append(timeMessage)

	messages.append("{}\n\n".format(
		string_utils.getCurrentPlayString(game)
	))

	if diffMessage is not None:
		messages.append(diffMessage)

	playSummary.play = play
	playSummary.result = result['result'] if result is not None else None
	playSummary.actualResult = actualResult
	if actualResult in [Result.TURNOVER]:
		playSummary.yards = None
	else:
		playSummary.yards = yards
	playSummary.playTime = timeOffClock

	if success:
		driveList = utils.appendPlay(game, playSummary)
		if driveList is not None:
			driveSummary = utils.summarizeDrive(driveList)
			field = drive_graphic.makeField(driveList)
			driveImageUrl = drive_graphic.uploadField(field, game.thread, str(len(game.status.plays) - 2))
			game.status.drives.append({'summary': driveSummary, 'url': driveImageUrl})
			messages.append(f"Drive: [{str(driveSummary)}]({driveImageUrl})")

	playString = string_utils.renderPlays(game)
	if game.playGist is None:
		game.playGist = utils.paste("Play summary", playString, static.GIST_USERNAME, static.GIST_TOKEN)
	else:
		utils.edit_paste("Play summary", playString, game.playGist, static.GIST_USERNAME, static.GIST_TOKEN)

	return success, '\n\n'.join(messages)


def executeDelayOfGame(game):
	utils.setLogGameID(game.thread, game)

	log.debug("Game past playclock: {}".format(game.thread))
	utils.cycleStatus(game, "DelayOfGame")
	game.status.state(game.status.waitingOn).playclockPenalties += 1
	penaltyMessage = "{} has not sent their number in over 24 hours, playclock penalty. This is their {} penalty.".format(
		string_utils.getCoachString(game, game.status.waitingOn),
		string_utils.getNthWord(game.status.state(game.status.waitingOn).playclockPenalties))

	if game.status.state(game.status.waitingOn).playclockPenalties >= 3:
		log.debug("3 penalties, game over")
		result = utils.endGame(game, game.team(game.status.waitingOn.negate()).name)
		resultMessage = "They forfeit the game. {} has won!\n\n{}".format(
			string_utils.flair(game.team(game.status.waitingOn.negate())), result)

	else:
		if utils.isGameOvertime(game):
			forceEightPointTouchdown(game, game.status.possession)
			resultMessage = overtimeTurnover(game)
			if game.status.waitingAction != Action.END:
				utils.sendDefensiveNumberMessage(game)
		else:
			forceEightPointTouchdown(game, game.status.waitingOn.negate())
			setStateKickoff(game, game.status.waitingOn.negate())
			game.status.waitingOn.reverse()
			utils.sendDefensiveNumberMessage(game)
			resultMessage = "Automatic touchdown and two point conversion, {} has the ball.".format(
				string_utils.flair(game.team(game.status.waitingOn)))

	utils.sendGameComment(game, "{}\n\n{}".format(penaltyMessage, resultMessage), None, False)
	utils.setGamePlayed(game)
	utils.updateGameThread(game)

	utils.clearLogGameID()
