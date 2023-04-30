import logging.handlers
import praw
import configparser
import traceback

import static

log = logging.getLogger("bot")
reddit = None
noWrite = False


def init(user):
	global reddit

	try:
		reddit = praw.Reddit(
			user,
			user_agent=static.USER_AGENT)
	except configparser.NoSectionError:
		log.error("User "+user+" not in praw.ini, aborting")
		return False

	static.ACCOUNT_NAME = str(reddit.user.me()).lower()

	log.info("Logged into reddit as /u/" + static.ACCOUNT_NAME)

	config_keys = [
		{'var': "GIST_USERNAME", 'name': "gist_username", 'optional': False},
		{'var': "GIST_TOKEN", 'name': "gist_token", 'optional': False},
		{'var': "CLOUDINARY_KEY", 'name': "cloudinary_key", 'optional': False},
		{'var': "CLOUDINARY_SECRET", 'name': "cloudinary_secret", 'optional': False},
		{'var': "WEBHOOK_MAIN", 'name': "webhook_main", 'optional': True},
		{'var': "WEBHOOK_FCS", 'name': "webhook_fcs", 'optional': True},
		{'var': "WEBHOOK_D2", 'name': "webhook_d2", 'optional': True},
	]
	for key in config_keys:
		if reddit.config.CONFIG.has_option(user, key['name']):
			setattr(static, key['var'], reddit.config.CONFIG[user][key['name']])
		else:
			if key['optional']:
				log.warning(f"{key['name']} key not in config, aborting")
			else:
				log.error(f"{key['name']} key not in config, aborting")
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
		reddit.redditor(recipient).message(
			subject=subject,
			message=message
		)
		results.append(getRecentSentMessage())

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


def setWikiPage(subreddit, pageName, content):
	wikiPage = reddit.subreddit(subreddit).wiki[pageName]
	global noWrite
	if not noWrite:
		wikiPage.edit(content)


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
	except praw.exceptions.RedditAPIException as err:
		if err.error_type == 'DELETED_COMMENT':
			log.info(f"Unable to reply, comment deleted: {message.id}")
			log.info(traceback.format_exc())
		else:
			log.warning(f"Reddit API exception sending message: {err}")
			log.warning(traceback.format_exc())
	except Exception as err:
		log.warning(f"Error sending message: {err}")
		log.warning(traceback.format_exc())
		return None


def getRecentSentMessage():
	return next(reddit.inbox.sent(limit=1))


def getThingFromFullname(fullname):
	if fullname.startswith("t1"):
		return getComment(fullname[3:])
	elif fullname.startswith("t4"):
		return getMessage(fullname[3:])
	else:
		log.debug("Not a valid fullname: {}".format(fullname))
		return None
