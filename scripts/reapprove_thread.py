import praw
import discord_logging

log = discord_logging.init_logging()


def reapprove_thread(submission):
	log.info(f"Processing submission {submission.id} with {submission.num_comments} comments")
	submission.comments.replace_more(limit=None)
	all_comments = submission.comments.list()
	log.info(f"Fetched {len(all_comments)} comments")

	removed_bot_comments = []
	for comment in all_comments:
		try:
			if comment.author.name == "NFCAAOfficialRefBot" and comment.banned_by is True:
				removed_bot_comments.append(comment)
		except Exception as err:
			log.warning(f"Couldn't reapprove comment {comment.id}: {err}")

	log.info(f"Found {len(removed_bot_comments)} removed bot comments")

	j = 0
	for comment in removed_bot_comments:
		comment.mod.approve()
		j += 1
		if j % 50 == 0:
			log.info(f"{j}/{len(removed_bot_comments)}")

	log.info(f"Done {j}/{len(removed_bot_comments)}")


reddit = praw.Reddit("NFCAAOfficialRefBot", user_agent="test agent")

i = 0
for submission in reddit.user.me().submissions.new(limit=None):
	reapprove_thread(submission)
	i += 1
	log.info(f"Submission {i}")
