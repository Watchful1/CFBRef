import logging.handlers
from datetime import datetime

import wiki
import utils
import classes
import globals
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

log = logging.getLogger("bot")


def scoreForTeam(game, points, homeAway):
	oldScore = game.status.state(homeAway).points
	game.status.state(homeAway).points += points
	log.debug("Score for {} changed from {} to {}".format(homeAway.name(), oldScore, game.status.state(homeAway).points))
	if len(game.status.state(homeAway).quarters) < game.status.quarter:
		game.status.state(homeAway).quarters.append(0)
	game.status.state(homeAway).quarters[game.status.quarter - 1] += points


def setStateTouchback(game, homeAway):
	log.debug("Setting state to touchback for: {}".format(homeAway))
	game.status.location = 25
	game.status.down = 1
	game.status.yards = 10
	game.status.possession = homeAway.copy()
	game.status.waitingAction = Action.PLAY
	game.status.waitingOn = homeAway.copy()


def setStateKickoff(game, homeAway):
	log.debug("Setting state to kickoff for: {}".format(homeAway))
	game.status.location = 35
	game.status.down = 1
	game.status.yards = 10
	game.status.timeRunoff = False
	game.status.possession = homeAway.copy()
	game.status.waitingAction = Action.KICKOFF
	game.status.waitingOn = homeAway.copy()


def setStateOvertimeDrive(game, homeAway):
	log.debug("Setting state to overtime drive for: {}".format(homeAway))
	if game.status.overtimePossession is None:
		game.status.overtimePossession = 1

	setStateTouchback(game, homeAway)
	game.status.location = 75


def forceTouchdown(game, homeAway):
	log.debug("Forcing touchdown for: {}".format(homeAway))
	scoreForTeam(game, 7, homeAway)


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
		return "End of the drive. {} has possession now".format(utils.flair(game.team(game.status.possession)))
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
				return "It is the end of the 6th quarter in an overtime forced by the game clock and the score is still tied. " \
				       "I'm flipping a coin to determine the victor. {} has won!\n\n{}".format(utils.flair(game.team(victor)), output)
			else:
				log.debug("End of second overtime possession, still tied, starting new quarter")
				game.status.overtimePossession = 1
				game.status.quarter += 1
				setStateOvertimeDrive(game, game.status.receivingNext)
				game.status.receivingNext.reverse()
				return "It's still tied! Going to the {} quarter.".format(utils.getNthWord(game.status.quarter))

		else:
			log.debug("End of game")
			if game.status.state(T.home).points > game.status.state(T.away).points:
				victor = HomeAway(T.home)
			else:
				victor = HomeAway(T.away)
			output = utils.endGame(game, game.team(victor).name)
			return "That's the end of the game. {} has won!\n\n".format(utils.flair(game.team(victor)), output)

	else:
		log.warning("Something went wrong. Invalid overtime possession: {}".format(game.status.overtimePossession))


def scoreSafety(game, homeAway):
	scoreForTeam(game, 2, homeAway)
	setStateKickoff(game, homeAway.negate())


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
		log.warning("{} is not a valid play".format(play))
		return None

	log.debug("Getting play result for: {}".format(play))
	if play in classes.movementPlays:
		offense = game.team(game.status.possession).offense
		defense = game.team(game.status.possession.negate()).defense
		log.debug("Movement play offense, defense: {} : {}".format(offense, defense))
		playMajorRange = playDict[offense][defense]
	else:
		playMajorRange = playDict

	playMinorRange = findNumberInRangeDict(100 - game.status.location, playMajorRange)
	return findNumberInRangeDict(number, playMinorRange)


def getTimeAfterForOffense(game, homeAway):
	offenseType = game.team(homeAway).offense
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


def betweenPlayRunoff(game, actualResult, offenseHomeAway, timeOption):
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
			if actualResult == Result.KNEEL:
				timeOffClock = 39
			elif timeOption == TimeOption.CHEW:
				timeOffClock = 35
			elif timeOption == TimeOption.HURRY:
				timeOffClock = 5
			else:
				timeOffClock = getTimeAfterForOffense(game, offenseHomeAway)

	log.debug("Between play runoff: {} : {} : {}".format(game.status.clock, timeOffClock, game.status.timeRunoff))
	game.status.clock -= timeOffClock
	game.status.timeRunoff = False


def updateTime(game, play, result, actualResult, yards, offenseHomeAway, timeOption):
	log.debug("Updating time with: {} : {} : {} : {} : {} : {}".format(play, result, actualResult, yards, offenseHomeAway, timeOption))
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
			if actualResult == Result.KNEEL:
				timeOffClock = 39
			elif timeOption == TimeOption.CHEW:
				timeOffClock = 35
			elif timeOption == TimeOption.HURRY:
				timeOffClock = 5
			else:
				timeOffClock = getTimeAfterForOffense(game, offenseHomeAway)

	if actualResult in [Result.TOUCHDOWN, Result.TOUCHBACK, Result.SAFETY] and play not in classes.kickoffPlays:
		timeResult = Result.GAIN
	elif actualResult == Result.TURNOVER and result == Result.GAIN:
		timeResult = Result.GAIN
	else:
		timeResult = actualResult

	game.status.timeRunoff = False
	if actualResult == Result.SPIKE:
		timeOffClock += 3
	elif play == Play.PAT:
		timeOffClock += 0
	elif play == Play.TWO_POINT:
		timeOffClock += 0
	else:
		if actualResult == Result.KNEEL:
			timeOffClock += 1
		else:
			timeOffClock += getTimeByPlay(play, timeResult, yards)

		if actualResult in [Result.GAIN, Result.KNEEL]:
			game.status.timeRunoff = True

	log.debug("Time off clock: {} : {} : {}".format(game.status.clock, timeOffClock, game.status.timeRunoff))

	game.status.clock -= timeOffClock
	timeMessage = "{} left".format(utils.renderTime(game.status.clock))

	if game.status.clock <= 0 and game.status.waitingAction not in [Action.CONVERSION]:
		log.debug("End of quarter: {}".format(game.status.quarter))
		actualTimeOffClock = timeOffClock + game.status.clock
		if game.status.quarter == 1:
			timeMessage = "end of the first quarter"
			game.status.timeRunoff = False
		elif game.status.quarter == 3:
			timeMessage = "end of the third quarter"
			game.status.timeRunoff = False
		else:
			if game.status.quarter == 4:
				if game.status.state(T.home).points == game.status.state(T.away).points:
					log.debug("Score tied at end of 4th, going to overtime")
					timeMessage = "end of regulation. The score is tied, we're going to overtime!"
					if game.deadline > datetime.utcnow():
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
					timeMessage = "that's the end of the game! {} has won!\n\n{}".format(utils.flair(game.team(victor)), output)
				game.status.clock = 0
			else:
				if game.status.quarter == 2:
					log.debug("End of half")
					timeMessage = "end of the first half"

				setStateKickoff(game, game.status.receivingNext.negate())
				game.status.receivingNext.reverse()
				game.status.state(T.home).timeouts = 3
				game.status.state(T.away).timeouts = 3

		if game.status.quarterType != QuarterType.END:
			game.status.quarter += 1
			game.status.clock = globals.quarterLength
	else:
		actualTimeOffClock = timeOffClock

	utils.addStat(game, 'posTime', actualTimeOffClock, offenseHomeAway)

	return "The play took {} seconds, {}".format(timeOffClock, timeMessage), timeOffClock


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

		return Result.TOUCHDOWN, 100 - previousLocation, "{} with a {} yard {} into the end zone for a touchdown!".format(game.team(game.status.possession).name, yards, play.name.lower())
	elif game.status.location <= 0:
		log.debug("Ball went back over the line, safety for the defense")

		utils.addStatRunPass(game, play, previousLocation * -1)
		scoreSafety(game, game.status.possession.negate())

		if play == Play.RUN:
			resultMessage = "The runner is taken down in the end zone for a safety."
		elif play == Play.PASS:
			resultMessage = "Sack! The quarterback is taken down in the endzone for a safety."
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
			return Result.GAIN, game.status.location - previousLocation, "{} play for {} yards, first down".format(play.name.lower().capitalize(), yards)
		else:
			log.debug("Not a first down, incrementing down")
			game.status.down += 1
			if game.status.down > 4:
				log.debug("Turnover on downs")
				if incomplete:
					resultMessage = "The pass is incomplete. Turnover on downs"
				else:
					resultMessage = "{} play for {} yards, but that's not enough for the first down. Turnover on downs".format(play.name.lower().capitalize(), yards)

				if utils.isGameOvertime(game):
					resultMessage = "{}\n\n{}".format(resultMessage, overtimeTurnover(game))
				else:
					turnover(game)
				return Result.TURNOVER, game.status.location - previousLocation, resultMessage
			else:
				log.debug("Now {} down and {}".format(utils.getDownString(game.status.down), yardsRemaining))
				game.status.yards = yardsRemaining
				if incomplete:
					resultMessage = "The pass is incomplete. {} and {}".format(utils.getDownString(game.status.down), yardsRemaining)
				else:
					resultMessage = "{} play for {} yards, {} and {}".format(
						play.name.lower().capitalize(),
						yards, utils.getDownString(game.status.down),
						"goal" if game.status.location + yardsRemaining >= 100 else yardsRemaining)

				return Result.GAIN, game.status.location - previousLocation, resultMessage


def executePunt(game, yards):
	log.debug("Ball punted for {} yards".format(yards))
	game.status.location = game.status.location + yards
	if game.status.location >= 100:
		log.debug("Punted into the end zone, touchback")
		setStateTouchback(game, game.status.possession.negate())
		if game.status.location > 110:
			return "The punt goes out the back of the end zone, touchback"
		else:
			return "The punt goes into the end zone, touchback"
	else:
		log.debug("Punt caught, setting up turnover")
		if utils.isGameOvertime(game):
			return overtimeTurnover(game)
		else:
			turnover(game)
			return "It's a {} yard punt".format(yards)


def executePlay(game, play, number, timeOption):
	startingPossessionHomeAway = game.status.possession.copy()
	actualResult = None
	result = None
	yards = None
	resultMessage = "Something went wrong, I should never have reached this"
	diffMessage = None
	success = True
	timeMessage = None

	playSummary = PlaySummary()
	playSummary.down = game.status.down
	playSummary.toGo = game.status.yards
	playSummary.location = game.status.location
	playSummary.offNum = number
	playSummary.posHome = game.status.possession.isHome

	if play in classes.conversionPlays:
		numberResult, diffMessage, defenseNumber = getNumberDiffForGame(game, number)
		playSummary.defNum = defenseNumber

		log.debug("Executing conversion play: {}".format(play))
		result = getPlayResult(game, play, numberResult)
		actualResult = result['result']

		if result['result'] == Result.TWO_POINT:
			log.debug("Successful two point conversion")
			resultMessage = "The two point conversion is successful"
			scoreTwoPoint(game, game.status.possession)
			if utils.isGameOvertime(game):
				timeMessage = overtimeTurnover(game)
			else:
				setStateKickoff(game, game.status.possession)

		elif result['result'] == Result.PAT:
			log.debug("Successful PAT")
			resultMessage = "The PAT was successful"
			scorePAT(game, game.status.possession)
			if utils.isGameOvertime(game):
				timeMessage = overtimeTurnover(game)
			else:
				setStateKickoff(game, game.status.possession)

		elif result['result'] == Result.KICKOFF:
			log.debug("Attempt unsuccessful")
			if play == Play.TWO_POINT:
				resultMessage = "The two point conversion attempt was unsuccessful"
			elif play == Play.PAT:
				resultMessage = "The PAT attempt was unsuccessful"
			else:
				resultMessage = "Conversion unsuccessful"
			if utils.isGameOvertime(game):
				timeMessage = overtimeTurnover(game)
			else:
				setStateKickoff(game, game.status.possession)

		game.status.defensiveNumber = None

	elif play in classes.kickoffPlays:
		numberResult, diffMessage, defenseNumber = getNumberDiffForGame(game, number)
		playSummary.defNum = defenseNumber

		log.debug("Executing kickoff play: {}".format(play))
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
				resultMessage = "{} yard kick.".format(yards)

		elif result['result'] == Result.GAIN:
			if 'yards' not in result:
				log.warning("Result is a dropped kick, but I couldn't find any yards")
				resultMessage = "The receiver drops the kick, but something went wrong and I couldn't find where"
				success = False
			else:
				log.debug("Result is a dropped kick of {} yards".format(result['yards']))
				yards = result['yards']
				game.status.location = game.status.location + yards
				resultMessage = "It's dropped! Recovered by {} on the {}".format(game.team(game.status.possession).name, utils.getLocationString(game))
				game.status.waitingAction = Action.PLAY

		elif result['result'] == Result.TOUCHBACK:
			log.debug("Result is a touchback")
			setStateTouchback(game, game.status.possession.negate())
			resultMessage = "The kick goes into the end zone, touchback."

		elif result['result'] == Result.TOUCHDOWN:
			log.debug("Result is a touchdown")
			resultMessage = "It's dropped! The kicking team recovers and runs it into the end zone! Touchdown {}!".format(game.team(game.status.possession).name)
			scoreTouchdown(game, game.status.possession)

		elif result['result'] == Result.TURNOVER_TOUCHDOWN:
			log.debug("Result is a run back for touchdown")
			resultMessage = "It's run all the way back! Touchdown {}!".format(game.team(game.status.possession.negate()).name)
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
			result['result'] = Result.PUNT
			actualResult = Result.PUNT

		if result['result'] == Result.GAIN:
			if play == Play.PUNT:
				log.debug("Muffed punt. Ball moved from {} to {}".format(game.status.location, game.status.location + result['yards']))
				game.status.location = game.status.location + result['yards']
				game.status.yards = 10
				game.status.down = 1
				yards = result['yards']
				resultMessage = "The receiver drops the ball! {} recovers on the {}.".format(game.team(game.status.possession).name, utils.getLocationString(game))

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
			resultMessage = "It's a {} into the endzone! Touchdown {}!".format(play.name.lower(), game.team(game.status.possession).name)
			previousLocation = game.status.location
			utils.addStatRunPass(game, play, 100 - previousLocation)
			scoreTouchdown(game, game.status.possession)
			yards = 100 - previousLocation

		elif result['result'] == Result.FIELD_GOAL:
			log.debug("Result is a field goal")
			resultMessage = "The {} yard field goal is good!".format(100 - game.status.location + 17)
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

		elif result['result'] in [Result.TURNOVER, Result.MISS]:
			log.debug("Play results in a turnover")
			if play == Play.RUN:
				utils.addStat(game, 'turnoverFumble', 1)
				resultMessage = "Fumble! The ball is dropped, {} recovers!".format(game.team(game.status.possession.negate()).name)
			elif play == Play.PASS:
				utils.addStat(game, 'turnoverInterceptions', 1)
				resultMessage = "Picked off! The pass is intercepted, {} ball!".format(game.team(game.status.possession.negate()).name)
			elif play == Play.FIELD_GOAL:
				if result['result'] == Result.TURNOVER:
					utils.addStat(game, 'turnoverFumble', 1)
					resultMessage = "It's blocked!"
				else:
					resultMessage = "The kick is wide."

			elif play == Play.PUNT:
				utils.addStat(game, 'turnoverFumble', 1)
				resultMessage = "It's blocked!"
			else:
				utils.addStat(game, 'turnoverFumble', 1)
				resultMessage = "It's a turnover!"
			if utils.isGameOvertime(game):
				timeMessage = overtimeTurnover(game)
			else:
				turnover(game)

		elif result['result'] == Result.TURNOVER_TOUCHDOWN:
			log.debug("Play results in a turnover and run back")
			if play == Play.RUN:
				utils.addStat(game, 'turnoverFumble', 1)
				resultMessage = "Fumble! The ball is dropped and it's run all the way back. Touchdown {}!".format(game.team(game.status.possession.negate()).name)
			elif play == Play.PASS:
				utils.addStat(game, 'turnoverInterceptions', 1)
				resultMessage = "Picked off! The pass is intercepted and it's run all the way back. Touchdown {}!".format(game.team(game.status.possession.negate()).name)
			elif play == Play.FIELD_GOAL or play == Play.PUNT:
				utils.addStat(game, 'turnoverFumble', 1)
				resultMessage = "It's blocked! The ball is picked up and run all the back. Touchdown {}!".format(game.team(game.status.possession.negate()).name)
			else:
				utils.addStat(game, 'turnoverFumble', 1)
				resultMessage = "It's a turnover and run back for a touchdown!"
			yards = game.status.location
			scoreTouchdown(game, game.status.possession.negate())
			if utils.isGameOvertime(game):
				output = utils.endGame(game, game.team(game.status.possession).name)
				timeMessage = "Game over! {} wins!\n\n{}".format(utils.flair(game.team(game.status.possession)), output)

		game.status.defensiveNumber = None

	elif play in classes.timePlays:
		if play == Play.KNEEL:
			log.debug("Running kneel play")
			actualResult = Result.KNEEL
			game.status.down += 1
			if game.status.down > 4:
				log.debug("Turnover on downs")
				if utils.isGameOvertime(game):
					timeMessage = overtimeTurnover(game)
				else:
					turnover(game)
				resultMessage = "Turnover on downs"
			else:
				resultMessage = "The quarterback takes a knee"

		elif play == Play.SPIKE:
			log.debug("Running spike play")
			actualResult = Result.SPIKE
			game.status.down += 1
			if game.status.down > 4:
				log.debug("Turnover on downs")
				if utils.isGameOvertime(game):
					timeMessage = overtimeTurnover(game)
				else:
					turnover(game)
				resultMessage = "Turnover on downs"
			else:
				resultMessage = "The quarterback spikes the ball"
		result = {'result': actualResult}

	else:
		log.debug("Something went wrong, invalid play: {}".format(play))
		resultMessage = "Something went wrong, invalid play: {}".format(play)
		success = False

	messages = [resultMessage]
	timeOffClock = None
	if actualResult is not None and game.status.quarterType == QuarterType.NORMAL:
		if timeMessage is None:
			timeMessage, timeOffClock = updateTime(game, play, result['result'], actualResult, yards, startingPossessionHomeAway, timeOption)

	if timeMessage is not None:
		messages.append(timeMessage)

	if diffMessage is not None:
		messages.append(diffMessage)

	playSummary.play = play
	playSummary.result = result['result'] if result is not None else None
	playSummary.actualResult = actualResult
	if actualResult in [Result.TURNOVER]:
		playSummary.yards = None
	else:
		playSummary.yards = yards
	playSummary.time = timeOffClock

	if success:
		game.plays.append(playSummary)



	return success, '\n\n'.join(messages)
