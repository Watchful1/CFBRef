import logging.handlers
from datetime import datetime

import wiki
import utils
import globals
import database

log = logging.getLogger("bot")


def scoreForTeam(game, points, homeAway):
	oldScore = game['score'][homeAway]
	game['score'][homeAway] += points
	log.debug("Score for {} changed from {} to {}".format(homeAway, oldScore, game['score'][homeAway]))
	game['score']['quarters'][game['status']['quarter'] - 1][homeAway] += points


def setStateTouchback(game, homeAway):
	if homeAway not in ['home', 'away']:
		log.warning("Bad homeAway in setStateTouchback: {}".format(homeAway))
		return
	game['status']['location'] = 25
	game['status']['down'] = 1
	game['status']['yards'] = 10
	game['status']['possession'] = homeAway
	game['status']['conversion'] = False
	game['waitingAction'] = 'play'
	game['waitingOn'] = homeAway


def setStateOvertimeDrive(game, homeAway):
	if homeAway not in ['home', 'away']:
		log.warning("Bad homeAway in setStateOvertimeDrive: {}".format(homeAway))
		return
	if game['status']['overtimePossession'] is None:
		game['status']['overtimePossession'] = 1

	setStateTouchback(game, homeAway)
	game['status']['location'] = 75


def forceTouchdown(game, homeAway):
	scoreForTeam(game, 7, homeAway)


def scoreTouchdown(game, homeAway):
	scoreForTeam(game, 6, homeAway)
	game['status']['location'] = 97
	game['status']['down'] = 1
	game['status']['yards'] = 10
	game['status']['possession'] = homeAway
	game['status']['conversion'] = True
	game['waitingAction'] = 'play'
	game['waitingOn'] = homeAway


def scoreFieldGoal(game, homeAway):
	scoreForTeam(game, 3, homeAway)


def scoreTwoPoint(game, homeAway):
	scoreForTeam(game, 1, homeAway)


def scorePAT(game, homeAway):
	scoreForTeam(game, 1, homeAway)


def turnover(game):
	game['status']['down'] = 1
	game['status']['yards'] = 10
	game['status']['possession'] = utils.reverseHomeAway(game['status']['possession'])
	game['status']['location'] = 100 - game['status']['location']
	game['waitingAction'] = 'play'
	game['waitingOn'] = utils.reverseHomeAway(game['waitingOn'])


def overtimeTurnover(game):
	log.debug("Running overtime turnover")
	if game['status']['overtimePossession'] == 1:
		log.debug("End of first overtime possession, starting second")
		game['status']['overtimePossession'] = 2
		setStateOvertimeDrive(game, utils.reverseHomeAway(game['status']['possession']))
		return "End of the drive. {} has possession now".format(utils.flair(game[game['status']['possession']]))
	elif game['status']['overtimePossession'] == 2:
		if game['score']['home'] == game['score']['away']:
			if game['status']['quarterType'] == 'overtimeTime' and game['status']['quarter'] >= 6:
				log.debug("End of 6th quarter in a time forced overtime, flipping coin for victor")
				game['status']['quarterType'] = 'end'
				game['waitingAction'] = 'end'
				if utils.coinToss():
					log.debug("Home has won")
					victor = 'home'
				else:
					log.debug("Away has won")
					victor = 'away'

				return "It is the end of the 6th quarter in an overtime forced by the game clock and the score is still tied. " \
				       "I'm flipping a coin to determine the victor. {} has won!".format(utils.flair(game[victor]))
			else:
				log.debug("End of second overtime possession, still tied, starting new quarter")
				game['status']['overtimePossession'] = 1
				game['status']['quarter'] += 1
				setStateOvertimeDrive(game, game['receivingNext'])
				game['receivingNext'] = utils.reverseHomeAway(game['receivingNext'])
				return "It's still tied! Going to the {} quarter.".format(utils.getNthWord(game['status']['quarter']))

		else:
			log.debug("End of game")
			game['status']['quarterType'] = 'end'
			game['waitingAction'] = 'end'
			if game['score']['home'] > game['score']['away']:
				victor = 'home'
			else:
				victor = 'away'
			return "That's the end of the game. {} has won!".format(utils.flair(game[victor]))

	else:
		log.warning("Something went wrong. Invalid overtime possession: {}".format(game['status']['overtimePossession']))


def scoreSafety(game, homeAway):
	scoreForTeam(game, 2, homeAway)
	setStateTouchback(game, utils.reverseHomeAway(homeAway))


def getNumberDiffForGame(game, offenseNumber):
	defenseNumber = database.getDefensiveNumber(game['dataID'])
	if defenseNumber is None:
		log.warning("Something went wrong, couldn't get a defensive number for that game")
		return -1

	straightDiff = abs(offenseNumber - defenseNumber)
	aroundRightDiff = abs(abs(1500-offenseNumber) + defenseNumber)
	aroundLeftDiff = abs(offenseNumber + abs(1500-defenseNumber))

	difference = min([straightDiff, aroundRightDiff, aroundLeftDiff])

	numberMessage = "Offense: {}\n\nDefense: {}\n\nDifference: {}".format(offenseNumber, defenseNumber, difference)
	log.debug("Offense: {} Defense: {} Result: {}".format(offenseNumber, defenseNumber, difference))

	return difference, numberMessage


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
	if play in globals.movementPlays:
		offense = game[game['status']['possession']]['offense']
		defense = game[utils.reverseHomeAway(game['status']['possession'])]['defense']
		log.debug("Movement play offense, defense: {} : {}".format(offense, defense))
		playMajorRange = playDict[offense][defense]
	else:
		playMajorRange = playDict

	playMinorRange = findNumberInRangeDict(100 - game['status']['location'], playMajorRange)
	return findNumberInRangeDict(number, playMinorRange)


def getTimeAfterForOffense(game, homeAway):
	offenseType = game[homeAway]['offense']
	if offenseType == "spread":
		return 10
	elif offenseType == "pro style":
		return 15
	elif offenseType == "option":
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
		log.warning("Could not get result in timePlay: {} : {}".format(play, result))
		return None

	timeObject = timePlay[result]
	if result == "gain":
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


def updateTime(game, play, result, yards, offenseHomeAway):
	if result in ['touchdown', 'touchback']:
		actualResult = "gain"
	else:
		actualResult = result
	if result == 'spike':
		timeOffClock = 1
	else:
		if result == 'kneel':
			timeOffClock = 1
		else:
			timeOffClock = getTimeByPlay(play, actualResult, yards)

		if result in ["gain", "kneel"]:
			if game['status']['requestedTimeout'][offenseHomeAway] == 'requested':
				log.debug("Using offensive timeout")
				game['status']['requestedTimeout'][offenseHomeAway] = 'used'
				game['status']['timeouts'][offenseHomeAway] -= 1
			elif game['status']['requestedTimeout'][utils.reverseHomeAway(offenseHomeAway)] == 'requested':
				log.debug("Using defensive timeout")
				game['status']['requestedTimeout'][utils.reverseHomeAway(offenseHomeAway)] = 'used'
				game['status']['timeouts'][utils.reverseHomeAway(offenseHomeAway)] -= 1
			else:
				if result == 'kneel':
					timeOffClock += 39
				else:
					timeOffClock += getTimeAfterForOffense(game, offenseHomeAway)
		log.debug("Time off clock: {} : {}".format(game['status']['clock'], timeOffClock))

	game['status']['clock'] -= timeOffClock
	timeMessage = "{} left".format(utils.renderTime(game['status']['clock']))

	if game['status']['clock'] < 0:
		log.debug("End of quarter: {}".format(game['status']['quarter']))
		actualTimeOffClock = timeOffClock + game['status']['clock']
		if game['status']['quarter'] == 1:
			timeMessage = "end of the first quarter"
		elif game['status']['quarter'] == 3:
			timeMessage = "end of the third quarter"
		else:
			if game['status']['quarter'] == 4:
				if game['score']['home'] == game['score']['away']:
					log.debug("Score tied at end of 4th, going to overtime")
					timeMessage = "end of regulation. The score is tied, we're going to overtime!"
					if database.getGameDeadline(game['dataID']) > datetime.utcnow():
						game['status']['quarterType'] = 'overtimeTime'
					else:
						game['status']['quarterType'] = 'overtimeNormal'
					game['waitingAction'] = 'overtime'
				else:
					log.debug("End of game")
					if game['score']['home'] > game['score']['away']:
						victor = 'home'
					else:
						victor = 'away'
					timeMessage = "that's the end of the game! {} has won!".format(utils.flair(game[victor]))
					game['status']['quarterType'] = 'end'
				game['status']['clock'] = 0
				game['waitingAction'] = 'end'
			else:
				if game['status']['quarter'] == 2:
					log.debug("End of half")
					timeMessage = "end of the first half"

				setStateTouchback(game, game['receivingNext'])
				game['receivingNext'] = utils.reverseHomeAway(game['receivingNext'])
				game['status']['timeouts'] = {'home': 3, 'away': 3}

		if game['status']['quarterType'] != 'end':
			game['status']['quarter'] += 1
			game['status']['clock'] = globals.quarterLength
	else:
		actualTimeOffClock = timeOffClock

	utils.addStat(game, 'posTime', actualTimeOffClock, offenseHomeAway)

	return "The play took {} seconds, {}".format(timeOffClock, timeMessage)


def executeGain(game, play, yards):
	if play not in globals.movementPlays:
		log.warning("This doesn't look like a valid movement play: {}".format(play))
		return "error", None, "Something went wrong trying to move the ball"

	previousLocation = game['status']['location']
	log.debug("Ball moved from {} to {}".format(previousLocation, previousLocation + yards))
	game['status']['location'] = previousLocation + yards
	if game['status']['location'] > 100:
		log.debug("Ball passed the line, touchdown offense")

		utils.addStatRunPass(game, play, 100 - previousLocation)
		scoreTouchdown(game, game['status']['possession'])

		return "touchdown", 100 - previousLocation, "{} with a {} yard {} into the end zone for a touchdown!".format(game[game['status']['possession']]['name'], yards, play)
	elif game['status']['location'] < 0:
		log.debug("Ball went back over the line, safety for the defense")

		utils.addStatRunPass(game, play, previousLocation * -1)
		scoreSafety(game, utils.reverseHomeAway(game['status']['possession']))

		if play == "run":
			resultMessage = "The runner is taken down in the end zone for a safety."
		elif play == "pass":
			resultMessage = "Sack! The quarterback is taken down in the endzone for a safety."
		else:
			resultMessage = "It's a safety!"

		return "touchback", 0 - previousLocation, resultMessage
	else:
		log.debug("Ball moved, but didn't enter an endzone, checking and updating play status")

		utils.addStatRunPass(game, play, yards)
		yardsRemaining = game['status']['yards'] - yards

		if yardsRemaining <= 0:
			log.debug("First down")
			game['status']['yards'] = 10
			game['status']['down'] = 1
			return "gain", game['status']['location'] - previousLocation, "{} play for {} yards, first down".format(play.capitalize(), yards)
		else:
			log.debug("Not a first down, incrementing down")
			game['status']['down'] += 1
			if game['status']['down'] > 4:
				log.debug("Turnover on downs")
				turnover(game)
				return "turnover", game['status']['location'] - previousLocation, "{} play for {} yards, but that's not enough for the first down. Turnover on downs".format(play.capitalize(), yards)
			else:
				log.debug("Now {} down and {}".format(utils.getDownString(game['status']['down']), yardsRemaining))
				game['status']['yards'] = yardsRemaining
				return "gain", game['status']['location'] - previousLocation, "{} play for {} yards, {} and {}".format(play.capitalize(), yards, utils.getDownString(game['status']['down']), yardsRemaining)


def executePunt(game, yards):
	log.debug("Ball punted for {} yards".format(yards))
	game['status']['location'] = game['status']['location'] + yards
	if game['status']['location'] > 100:
		log.debug("Punted into the end zone, touchback")
		setStateTouchback(game, utils.reverseHomeAway(game['status']['possession']))
		if game['status']['location'] > 110:
			return "The punt goes out the back of the end zone, touchback"
		else:
			return "The punt goes into the end zone, touchback"
	else:
		log.debug("Punt caught, setting up turnover")
		turnover(game)
		return "It's a {} yard punt".format(yards)


def executePlay(game, play, number, numberMessage):
	startingPossessionHomeAway = game['status']['possession']
	actualResult = None
	yards = None
	resultMessage = "Something went wrong, I should never have reached this"
	diffMessage = None
	success = True
	timeMessage = None
	if game['status']['conversion']:
		if play in globals.conversionPlays:
			if number == -1:
				log.debug("Trying to execute a normal play, but didn't have a number")
				resultMessage = numberMessage
				success = False

			else:
				numberResult, diffMessage = getNumberDiffForGame(game, number)

				log.debug("Executing conversion play: {}".format(play))
				result = getPlayResult(game, play, numberResult)
				if result['result'] == 'twoPoint':
					log.debug("Successful two point conversion")
					resultMessage = "The two point conversion is successful"
					scoreTwoPoint(game, game['status']['possession'])
					if utils.isGameOvertime(game):
						timeMessage = overtimeTurnover(game)
					else:
						setStateTouchback(game, utils.reverseHomeAway(game['status']['possession']))

				elif result['result'] == 'pat':
					log.debug("Successful PAT")
					resultMessage = "The PAT was successful"
					scorePAT(game, game['status']['possession'])
					if utils.isGameOvertime(game):
						timeMessage = overtimeTurnover(game)
					else:
						setStateTouchback(game, utils.reverseHomeAway(game['status']['possession']))

				elif result['result'] == 'touchback':
					log.debug("Attempt unsuccessful")
					if play == "twoPoint":
						resultMessage = "The two point conversion attempt was unsuccessful"
					elif play == "pat":
						resultMessage = "The PAT attempt was unsuccessful"
					else:
						resultMessage = "Conversion unsuccessful"
					if utils.isGameOvertime(game):
						timeMessage = overtimeTurnover(game)
					else:
						setStateTouchback(game, utils.reverseHomeAway(game['status']['possession']))

				database.clearDefensiveNumber(game['dataID'])

		else:
			resultMessage = "It looks like you're trying to get the extra point after a touchdown, but this isn't a valid play"
			success = False
	else:
		if play in globals.normalPlays:
			if number == -1:
				log.debug("Trying to execute a normal play, but didn't have a number")
				resultMessage = numberMessage
				success = False

			else:
				numberResult, diffMessage = getNumberDiffForGame(game, number)

				log.debug("Executing normal play: {}".format(play))
				result = getPlayResult(game, play, numberResult)
				if result['result'] == 'gain':
					if 'yards' not in result:
						log.warning("Result is a gain, but I couldn't find any yards")
						resultMessage = "Result of play is a number of yards, but something went wrong and I couldn't find what number"
						success = False
					else:
						log.debug("Result is a gain of {} yards".format(result['yards']))
						gainResult, yards, resultMessage = executeGain(game, play, result['yards'])
						if gainResult != "error":
							if yards is not None:
								actualResult = gainResult
						else:
							success = False

				elif result['result'] == 'touchdown':
					log.debug("Result is a touchdown")
					resultMessage = "It's a {} into the endzone! Touchdown {}!".format(play, game[game['status']['possession']]['name'])
					previousLocation = game['status']['location']
					utils.addStatRunPass(game, play, 100 - previousLocation)
					scoreTouchdown(game, game['status']['possession'])
					actualResult = "touchdown"
					yards = 100 - previousLocation

				elif result['result'] == 'fieldGoal':
					log.debug("Result is a field goal")
					resultMessage = "The {} yard field goal is good!".format(100 - game['status']['location'] + 17)
					utils.addStat(game, 'fieldGoalsScored', 1)
					scoreFieldGoal(game, game['status']['possession'])
					if utils.isGameOvertime(game):
						timeMessage = overtimeTurnover(game)
					else:
						setStateTouchback(game, utils.reverseHomeAway(game['status']['possession']))
					actualResult = "fieldGoal"

				elif result['result'] == 'punt':
					if 'yards' not in result:
						log.warning("Result is a punt, but I couldn't find any yards")
						resultMessage = "Result of play is a successful punt, but something went wrong and I couldn't find how long a punt"
					log.debug("Successful punt of {} yards".format(result['yards']))
					if utils.isGameOvertime(game):
						log.warning("A punt happened in overtime, this shouldn't have happened")
						resultMessage = "A punt happened, but it's overtime. This shouldn't be possible."
					else:
						resultMessage = executePunt(game, result['yards'])
					actualResult = "punt"

				elif result['result'] == 'turnover':
					log.debug("Play results in a turnover")
					if play == "run":
						utils.addStat(game, 'turnoverInterceptions', 1)
						resultMessage = "Fumble! The ball is dropped, {} recovers!".format(game[utils.reverseHomeAway(game['status']['possession'])]['name'])
					elif play == "pass":
						utils.addStat(game, 'turnoverFumble', 1)
						resultMessage = "Picked off! The pass is intercepted, {} ball!".format(game[utils.reverseHomeAway(game['status']['possession'])]['name'])
					elif play == "fieldGoal" or play == "punt":
						utils.addStat(game, 'turnoverFumble', 1)
						resultMessage = "It's a miss!"
					else:
						utils.addStat(game, 'turnoverFumble', 1)
						resultMessage = "It's a turnover!"
					if utils.isGameOvertime(game):
						timeMessage = overtimeTurnover(game)
					else:
						turnover(game)
					actualResult = "turnover"

				elif result['result'] == 'turnoverTouchdown':
					log.debug("Play results in a turnover and run back")
					if play == "run":
						resultMessage = "Fumble! The ball is dropped and it's run all the way back. Touchdown {}!".format(game[utils.reverseHomeAway(game['status']['possession'])]['name'])
					elif play == "pass":
						resultMessage = "Picked off! The pass is intercepted and it's run all the way back. Touchdown {}!".format(game[utils.reverseHomeAway(game['status']['possession'])]['name'])
					elif play == "fieldGoal" or play == "punt":
						resultMessage = "It's blocked! The ball is picked up and run all the back. Touchdown {}!".format(game[utils.reverseHomeAway(game['status']['possession'])]['name'])
					else:
						resultMessage = "It's a turnover and run back for a touchdown!"
					scoreTouchdown(game, utils.reverseHomeAway(game['status']['possession']))
					actualResult = "turnoverTouchdown"
					if utils.isGameOvertime(game):
						timeMessage = "Game over! {} wins!".format(utils.flair(game[game['status']['possession']]))
						game['status']['quarterType'] = 'end'
						game['waitingAction'] = 'end'

				if success and play == 'fieldGoal':
					utils.addStat(game, 'fieldGoalsAttempted', 1)

				database.clearDefensiveNumber(game['dataID'])

		elif play in globals.timePlays:
			if play == 'kneel':
				log.debug("Running kneel play")
				actualResult = "kneel"
				game['status']['down'] += 1
				if game['status']['down'] > 4:
					log.debug("Turnover on downs")
					if utils.isGameOvertime(game):
						timeMessage = overtimeTurnover(game)
					else:
						turnover(game)
					resultMessage = "Turnover on downs"
				else:
					resultMessage = "The quarterback takes a knee"

			elif play == 'spike':
				log.debug("Running spike play")
				actualResult = "spike"
				game['status']['down'] += 1
				if game['status']['down'] > 4:
					log.debug("Turnover on downs")
					if utils.isGameOvertime(game):
						timeMessage = overtimeTurnover(game)
					else:
						turnover(game)
					resultMessage = "Turnover on downs"
				else:
					resultMessage = "The quarterback spikes the ball"

		else:
			resultMessage = "{} isn't a valid play at the moment".format(play)
			success = False

	messages = [resultMessage]
	if actualResult is not None:
		if timeMessage is not None:
			timeMessage = updateTime(game, play, actualResult, yards, startingPossessionHomeAway)

		messages.append(timeMessage)

	if diffMessage is not None:
		messages.append(diffMessage)

	return success, '\n\n'.join(messages)
