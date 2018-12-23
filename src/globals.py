from pytz import timezone

### Config ###
LOG_FOLDER_NAME = "logs"
SAVE_FOLDER_NAME = "games"
ARCHIVE_FOLDER_NAME = "gamesOld"
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
PASTEBIN_KEY = None
CLOUDINARY_BUCKET = "fakecfb"
CLOUDINARY_KEY = None
CLOUDINARY_SECRET = None


### Images ###
field_height = 212
field_width = 480


### Constants ###
datatag = " [](#datatag"
quarterLength = 7*60

### Log ###
logGameId = ""
game = None
