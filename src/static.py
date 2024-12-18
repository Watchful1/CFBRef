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

GIST_RESET = None
GIST_LIMITED = False
GIST_PENDING = set()


def get_webhook_for_conference(division):
	if division == "Division 2" and WEBHOOK_D2:
		return [WEBHOOK_D2]
	elif division == "FCS" and WEBHOOK_FCS:
		return [WEBHOOK_FCS]
	elif division == "FBS" and WEBHOOK_MAIN:
		return [WEBHOOK_MAIN]
	else:
		return []

### Images ###
field_height = 212
field_width = 480


### Constants ###
datatag = " [](#datatag"

### Log ###
logGameId = ""
game = None


## Lengths ##
FIELD_GOAL_ADDITIONAL_YARDAGE = 17
