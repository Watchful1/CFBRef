from classes import Play
from classes import Action

### Config ###
LOG_FOLDER_NAME = "logs"
SUBREDDIT = "FakeCollegeFootball"
CONFIG_SUBREDDIT = "FakeCollegeFootball"
USER_AGENT = "FakeCFBRef (by /u/Watchful1)"
OWNER = "watchful1"
LOOP_TIME = 2*60
DATABASE_NAME = "database.db"
SUBREDDIT_LINK = "https://www.reddit.com/r/{}/comments/".format(SUBREDDIT)
MESSAGE_LINK = "https://www.reddit.com/message/messages/"
ACCOUNT_NAME = "default"

### Constants ###
movementPlays = [Play.RUN, Play.PASS]
normalPlays = [Play.RUN, Play.PASS, Play.PUNT, Play.FIELD_GOAL]
timePlays = [Play.KNEEL, Play.SPIKE]
conversionPlays = [Play.PAT, Play.TWO_POINT]
kickoffPlays = [Play.KICKOFF_NORMAL, Play.KICKOFF_SQUIB, Play.KICKOFF_ONSIDE]
playActions = [Action.PLAY, Action.CONVERSION, Action.KICKOFF]
datatag = " [](#datatag"
quarterLength = 7*60

### Log ###
logGameId = ""
gameId = None