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

	if reddit.config.CONFIG.has_option(user, 'pastebin'):
		globals.PASTEBIN_KEY = reddit.config.CONFIG[user]['pastebin']
	else:
		log.error("Pastebin key not in config, aborting")
		return False

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
	results = []
	for recipient in recipients:
		try:
			reddit.redditor(recipient).message(
				subject=subject,
				message=message
			)
			results.append(getRecentSentMessage())
		except praw.exceptions.APIException:
			log.warning("User "+recipient+" doesn't exist")
			return []
		except Exception:
			log.warning("Couldn't sent message to "+recipient)
			log.warning(traceback.format_exc())
			return []

	return results


def replySubmission(id, message):
	try:
		submission = getSubmission(id)
		resultComment = submission.reply(message)
		return resultComment
	except Exception as err:
		log.warning(traceback.format_exc())
		return None


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


def getComment(id):
	return reddit.comment(id)


def getMessageStream():
	return reddit.inbox.stream()


def replyMessage(message, body):
	try:
		return message.reply(body)
	except Exception as err:
		log.warning(traceback.format_exc())
		return None


def getRecentSentMessage():
	return reddit.inbox.sent(limit=1).next()


def getThingFromFullname(fullname):
	if fullname.startswith("t1"):
		return getComment(fullname[3:])
	elif fullname.startswith("t4"):
		return getMessage(fullname[3:])
	else:
		log.debug("Not a valid fullname: {}".format(fullname))
		return None
