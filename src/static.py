from pytz import timezone

### Config ###
LOG_FOLDER_NAME = "logs"
SAVE_FOLDER_NAME = "games"
ARCHIVE_FOLDER_NAME = "gamesOld"
STRING_SUGGESTION_FILE = "suggestions.txt"
RESTART_REASON_FILE = "restarts.txt"
TEAMS_FILE = "teams.pickle"
SUBREDDIT = "FakeCollegeFootball"
CONFIG_SUBREDDIT = "FakeCollegeFootball"
USER_AGENT = "FakeCFBRef (by /u/Watchful1)"
OWNER = "watchful1"
LOOP_TIME = 2*60
DATABASE_NAME = "database.db"
SUBREDDIT_LINK = "https://www.reddit.com/r/{}/comments/".format(SUBREDDIT)
MESSAGE_LINK = "https://www.reddit.com/message/messages/"
ACCOUNT_NAME = "default"
EASTERN = timezone('US/Eastern')
GIST_USERNAME = None
GIST_TOKEN = None
GIST_BASE_URL = "https://gist.github.com/"
CLOUDINARY_BUCKET = "fakecfb"
CLOUDINARY_KEY = None
CLOUDINARY_SECRET = None

WEBHOOK_MAIN = None
WEBHOOK_FCS = None
WEBHOOK_D2 = None


def get_webhook_for_conference(division):
	if division == "Division 2":
		return WEBHOOK_D2
	elif division == "FBS":
		return WEBHOOK_FCS
	elif division is None:
		return WEBHOOK_MAIN
	else:
		return None

### Images ###
field_height = 212
field_width = 480


### Constants ###
datatag = " [](#datatag"
quarterLength = 7*60

### Log ###
logGameId = ""
game = None
