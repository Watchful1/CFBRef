import logging.handlers
import praw
import configparser
import traceback

import globals

log = logging.getLogger("bot")
reddit = None


def init(user):
	global reddit

	try:
		reddit = praw.Reddit(
			user,
			user_agent=globals.USER_AGENT)
	except configparser.NoSectionError:
		log.error("User "+user+" not in praw.ini, aborting")
		return False

	globals.ACCOUNT_NAME = str(reddit.user.me()).lower()

	log.info("Logged into reddit as /u/" + globals.ACCOUNT_NAME)
	return True


def getMessages():
	return reddit.inbox.unread(limit=100)


def getMessage(id):
	try:
		return reddit.inbox.message(id)
	except Exception:
		return None


def sendMessage(recipients, subject, message):
	if not isinstance(recipients, list):
		recipients = [recipients]
	success = True
	for recipient in recipients:
		try:
			reddit.redditor(recipient).message(
				subject=subject,
				message=message
			)
		except praw.exceptions.APIException:
			log.warning("User "+recipient+" doesn't exist")
			success = False
		except Exception:
			log.warning("Couldn't sent message to "+recipient)
			log.warning(traceback.format_exc())
			success = False

	return success



def getWikiPage(subreddit, pageName):
	wikiPage = reddit.subreddit(subreddit).wiki[pageName]

	return wikiPage.content_md


def submitSelfPost(subreddit, title, text):
	return reddit.subreddit(subreddit).submit(title=title, selftext=text)


def getSubmission(id):
	return reddit.submission(id=id)


def editThread(id, text):
	submission = getSubmission(id)
	submission.edit(text)
