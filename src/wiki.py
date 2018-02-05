import logging.handlers

import reddit
import globals

log = logging.getLogger("bot")

teams = {}
coaches = {}


def loadTeams(debug=False):
	teamsPage = reddit.getWikiPage(globals.CONFIG_SUBREDDIT, "teams")

	if debug:
		teamsPage = "\n".join([teamsPage,
		                       "testteam|Test Team|Spread|3-4|Watchful1",
		                       "testteam2|Test Team 2|Spread|3-4|Watchful12"])

	for teamLine in teamsPage.splitlines():
		items = teamLine.split('|')
		if len(items) < 5:
			log.warning("Could not parse team line: {}".format(teamLine))
			continue
		team = {'tag': items[0], 'name': items[1], 'offense': items[2].lower(), 'defense': items[3].lower(),
		        'coaches': []}
		for coach in items[4].lower().split(','):
			coach = coach.strip()
			team['coaches'].append(coach)
			coaches[coach] = team
		teams[team['tag']] = team


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
