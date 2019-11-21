import logging.handlers
import praw
import configparser
import traceback

import static

log = logging.getLogger("bot")
reddit = None


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
		{'var': "GIST_USERNAME", 'name': "gist_username"},
		{'var': "GIST_TOKEN", 'name': "gist_token"},
		{'var': "CLOUDINARY_KEY", 'name': "cloudinary_key"},
		{'var': "CLOUDINARY_SECRET", 'name': "cloudinary_secret"},
		{'var': "WEBHOOK_MAIN", 'name': "webhook_main"},
		{'var': "WEBHOOK_FCS", 'name': "webhook_fcs"},
		{'var': "WEBHOOK_FCS_2", 'name': "webhook_fcs_2"},
		{'var': "WEBHOOK_D2", 'name': "webhook_d2"},
		{'var': "WEBHOOK_D2_2", 'name': "webhook_d2_2"},
	]
	for key in config_keys:
		if reddit.config.CONFIG.has_option(user, key['name']):
			setattr(static, key['var'], reddit.config.CONFIG[user][key['name']])
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


def setWikiPage(subreddit, pageName, content):
	wikiPage = reddit.subreddit(subreddit).wiki[pageName]
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
