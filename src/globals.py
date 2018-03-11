from enum import Enum

### Config ###
LOG_FOLDER_NAME = "logs"
SUBREDDIT = "FakeCollegeFootball"
CONFIG_SUBREDDIT = "FakeCollegeFootball"
USER_AGENT = "FakeCFBRef (by /u/Watchful1)"
OWNER = "watchful1"
LOOP_TIME = 2*60
DATABASE_NAME = "database.db"
SUBREDDIT_LINK = "https://www.reddit.com/r/{}/comments/".format(SUBREDDIT)
ACCOUNT_NAME = "default"

### Constants ###
movementPlays = ['run', 'pass']
normalPlays = ['run', 'pass', 'punt', 'punt', 'fieldGoal']
timePlays = ['kneel', 'spike']
conversionPlays = ['pat', 'twoPoint']
datatag = "[](#datatag"
quarterLength = 7*60

### Log ###
logGameId = ""
gameId = None