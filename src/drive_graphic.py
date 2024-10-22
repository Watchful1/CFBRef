import logging.handlers
import traceback
from io import BytesIO

import cloudinary
from PIL import Image, ImageDraw
from cloudinary.uploader import upload

import static
from classes import Play, Result

log = logging.getLogger("bot")

FIELD_GRAPHIC_SCALE = int(static.field_width / 120)
ENDZONE_WIDTH_YARDS = 10
FIELD_WIDTH_YARDS = 100
LEFT_ENDZONE_START_X = 0
FIELD_START_X = ENDZONE_WIDTH_YARDS * FIELD_GRAPHIC_SCALE
FIELD_END_X = (ENDZONE_WIDTH_YARDS + FIELD_WIDTH_YARDS) * FIELD_GRAPHIC_SCALE
RIGHT_ENDZONE_END_X = (ENDZONE_WIDTH_YARDS + FIELD_WIDTH_YARDS + ENDZONE_WIDTH_YARDS) * FIELD_GRAPHIC_SCALE
FIELD_LINE_INTERVAL_X = 5 * FIELD_GRAPHIC_SCALE
FIELD_LINE_THICKNESS = 1 * FIELD_GRAPHIC_SCALE

DEFAULT_FIELD_COLOR = "green"
DEFAULT_FIELD_LINE_COLOR = "grey"
DEFAULT_ENDZONE_COLOR = "lightgrey"
DEFAULT_ENDZONE_BORDER_COLOR = "black"
DEFAULT_LINE_OF_SCRIMMAGE_COLOR = "white"
DEFAULT_RUN_COLOR = "red"
DEFAULT_PASS_COLOR = "blue"
DEFAULT_KICK_COLOR = "yellow"

# Seems like a good number to show on field, unlikely to be more plays in a drive
MAX_PLAY_COUNT = 42
# 212 // 42 = 5, should scale if resolution or max play count changes
SPACING_BETWEEN_PLAY_LINES = static.field_height // MAX_PLAY_COUNT
PLAY_LINE_THICKNESS = 212 // static.field_height  # 1 pixel thick when field height is 212 (default)


def init():
    cloudinary.config(
        cloud_name=static.CLOUDINARY_BUCKET,
        api_key=static.CLOUDINARY_KEY,
        api_secret=static.CLOUDINARY_SECRET
    )


def uploadField(field, gameId, driveNum):
    imageFile = BytesIO()
    field.save(imageFile, format='PNG')
    image = imageFile.getvalue()
    try:
        upload_result = upload(image, public_id=f"{gameId}/{driveNum}")
        return upload_result['secure_url']
    except Exception as err:
        log.warning("Couldn't upload drive image")
        log.warning(traceback.format_exc())
        return ""


def fill_in_box(draw: ImageDraw, x1: int, y1: int, x2: int, y2: int, color: str) -> ImageDraw:
    draw.rectangle([x1, y1, x2, y2], fill=color)
    return draw


def draw_vertical_line(draw: ImageDraw, x: int, y1: int, y2: int, color: str, thickness: int = 1) -> ImageDraw:
    line = ((x, y1), (x, y2))
    draw.line(line, fill=color, width=thickness)
    return draw


def draw_horizontal_line(draw: ImageDraw, x1: int, x2: int, y: int, color: str, thickness: int = 1) -> ImageDraw:
    line = ((x1, y), (x2, y))
    draw.line(line, fill=color, width=thickness)
    return draw


def get_true_x_position(yard_position: int, is_home: bool) -> int:
    """
    Get the true x position of a yardage location on the field
    :param yard_position: The yardage location on the field
    :param is_home: Whether this position is for the home team
    :return:
    """
    yard_position = int(yard_position)
    if not is_home:
        yard_position = FIELD_WIDTH_YARDS - yard_position

    yards_from_back_of_left_endzone = yard_position + ENDZONE_WIDTH_YARDS

    return yards_from_back_of_left_endzone * FIELD_GRAPHIC_SCALE  # Convert yards to pixels


def is_displayable_play(play) -> bool:
    enum_values = [_enum.value for _enum in [Play.RUN, Play.PASS, Play.FIELD_GOAL]]
    return play.play.value in enum_values


def draw_line_of_scrimmage(draw: ImageDraw, play) -> ImageDraw:
    line_of_scrimage_x = get_true_x_position(yard_position=play.location, is_home=play.posHome)
    draw = draw_vertical_line(draw=draw, x=line_of_scrimage_x, y1=0, y2=static.field_height,
                              color=DEFAULT_LINE_OF_SCRIMMAGE_COLOR, thickness=FIELD_LINE_THICKNESS)
    return draw


def draw_play_line(draw: ImageDraw,
                   play,
                   line_y_position: int,
                   run_color: str = DEFAULT_RUN_COLOR,
                   pass_color: str = DEFAULT_PASS_COLOR,
                   kick_color: str = DEFAULT_KICK_COLOR) -> ImageDraw:
    play_color = run_color
    if play.play.value == Play.RUN.value:
        play_color = run_color
    elif play.play.value == Play.PASS.value:
        play_color = pass_color
    elif play.play.value == Play.FIELD_GOAL.value:
        play_color = kick_color

    start_yardage = int(play.location)
    play_yards = 0 if not play.yards else int(play.yards)
    if play.play.value == Play.FIELD_GOAL.value:
        play_yards = static.field_width + 1  # Just draw a line off the edge of the screen for field goals
    end_yardage = start_yardage + play_yards

    start_x = get_true_x_position(yard_position=start_yardage, is_home=play.posHome)
    end_x = get_true_x_position(yard_position=end_yardage, is_home=play.posHome)

    draw = draw_horizontal_line(draw=draw, x1=start_x, x2=end_x, y=line_y_position, color=play_color,
                                thickness=PLAY_LINE_THICKNESS)

    return draw


def makeField(plays,
              field_color: str = DEFAULT_FIELD_COLOR,
              field_line_color: str = DEFAULT_FIELD_LINE_COLOR,
              run_color: str = DEFAULT_RUN_COLOR,
              pass_color: str = DEFAULT_PASS_COLOR,
              kick_color: str = DEFAULT_KICK_COLOR,
              home_team_color: str = None,
              away_team_color: str = None) -> Image:
    """
    Create a field image with the given plays

    :param plays: List of plays to display on the field
    :param field_color: Optional, override default color of the field
    :param field_line_color: Optional, override default color of the field lines
    :param run_color: Optional, override default color of run plays
    :param pass_color: Optional, override default color of pass plays
    :param kick_color: Optional, override default color of kick plays
    :param home_team_color: Optional, override default color of the home team (used for endzone)
    :param away_team_color: Optional, override default color of the away team (used for endzone)
    :return: Image of the field with the plays drawn
    """
    field = Image.new(mode='RGB', size=(static.field_width, static.field_height), color=field_color)
    draw = ImageDraw.Draw(field)

    home_endzone_color = home_team_color or DEFAULT_ENDZONE_COLOR
    away_endzone_color = away_team_color or DEFAULT_ENDZONE_COLOR

    # Draw endzones
    draw = fill_in_box(draw=draw, x1=LEFT_ENDZONE_START_X, x2=FIELD_START_X, y1=0, y2=static.field_height,
                       color=home_endzone_color)
    draw = fill_in_box(draw=draw, x1=FIELD_END_X, x2=RIGHT_ENDZONE_END_X, y1=0, y2=static.field_height,
                       color=away_endzone_color)

    # Draw main field
    draw = fill_in_box(draw=draw, x1=FIELD_END_X, x2=FIELD_END_X, y1=0, y2=static.field_height, color=field_color)

    # Draw yard lines
    for fifth_yard_line in range(FIELD_START_X, FIELD_END_X + 1, FIELD_LINE_INTERVAL_X):  # +1 to be inclusive
        # Use DEFAULT_ENDZONE_BORDER_COLOR for the endzone lines, otherwise use field_line_color for 5-yard lines
        color = DEFAULT_ENDZONE_BORDER_COLOR \
            if (fifth_yard_line == FIELD_START_X or fifth_yard_line == FIELD_END_X) else field_line_color
        draw = draw_vertical_line(draw=draw, x=fifth_yard_line, y1=0, y2=static.field_height, color=color,
                                  thickness=FIELD_LINE_THICKNESS)

    # Account for too many plays
    if len(plays) > MAX_PLAY_COUNT:
        # God help us if we ever have a drive with more than 42 plays
        # Invert the play list, grab the "first" (last) 42 plays, and invert it back
        plays = plays[::-1][:MAX_PLAY_COUNT][::-1]

    line_of_scrimmage_drawn = False

    # Draw play lines for each play
    # Currently only draws yardage-change plays (run, pass, field goal)
    play_y_position = SPACING_BETWEEN_PLAY_LINES
    for play in plays:
        # Skip plays that are not displayable
        if not is_displayable_play(play=play):
            continue

        # Draw the line of scrimmage at the start location of the first displayable play
        if not line_of_scrimmage_drawn:
            draw = draw_line_of_scrimmage(draw=draw, play=play)
            line_of_scrimmage_drawn = True

        # Draw the play line for a yardage-change play (including made field goal)
        draw = draw_play_line(draw=draw,
                              play=play,
                              line_y_position=play_y_position,
                              run_color=run_color,
                              pass_color=pass_color,
                              kick_color=kick_color)
        play_y_position += SPACING_BETWEEN_PLAY_LINES

    return field
