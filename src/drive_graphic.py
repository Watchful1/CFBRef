import logging.handlers
import traceback
from dataclasses import dataclass
from io import BytesIO
from typing import List

import cloudinary
from PIL import Image, ImageDraw
from cloudinary.uploader import upload

import static
from classes import Play, Result, PlaySummary

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
DEFAULT_RUN_COLOR = "red"
DEFAULT_PASS_COLOR = "blue"
DEFAULT_KICK_MADE_COLOR = "yellow"
DEFAULT_KICK_MISS_COLOR = "black"
DEFAULT_TURNOVER_COLOR = "orange"
DEFAULT_ALT_PLAY_COLOR = "purple"  # Used for plays that don't have a specific color (e.g. kneel, spike, delay of game)

# Seems like a good number to show on field, unlikely to be more plays in a drive
MAX_PLAY_COUNT = 42
# 212 // 42 = 5, should scale if resolution or max play count changes
SPACING_BETWEEN_PLAY_LINES = static.field_height // MAX_PLAY_COUNT
PLAY_LINE_THICKNESS = 212 // static.field_height  # 1 pixel thick when field height is 212 (default)


@dataclass
class GraphicColors:
    home_team_color: str
    away_team_color: str
    field_color: str
    field_line_color: str
    endzone_border_color: str
    pass_color: str
    run_color: str
    kick_made_color: str
    kick_miss_color: str
    turnover_color: str
    alt_color: str

    def get_play_color(self, play: PlaySummary):
        play_type = play.play
        play_result = play.actualResult

        if play_result in [Result.TURNOVER, Result.TURNOVER_TOUCHDOWN, Result.TURNOVER_PAT, Result.SAFETY]:
            return self.turnover_color

        if play_type == Play.RUN:
            return self.run_color  # Gain/loss doesn't matter for color
        elif play_type == Play.PASS:
            return self.pass_color  # Won't show incomplete passes
        elif play_type in [Play.FIELD_GOAL, Play.PAT]:
            return self.kick_miss_color if play_result == Result.MISS else self.kick_made_color
        elif play_type == Play.PUNT:
            if play_type == Play.PUNT and play_result == Result.GAIN:  # Recovered their own punt
                return self.kick_made_color
        else:
            return self.alt_color  # play.KNEEL, play.SPIKE, play.DELAY_OF_GAME

    def get_line_of_scrimmage_color(self, play: PlaySummary):
        return self.home_team_color if play.posHome else self.away_team_color


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


def is_displayable_play(play: PlaySummary) -> bool:
    # Display run/pass plays (regardless of gain/loss), field goals and PAT attempts (regardless of result),
    # and self-recovered punts
    return (play.play in [Play.RUN, Play.PASS, Play.FIELD_GOAL, Play.PAT]
            or (play.play == Play.PUNT and play.actualResult == Result.GAIN))


def draw_line_of_scrimmage(draw: ImageDraw, play: PlaySummary, colors: GraphicColors) -> ImageDraw:
    line_color = colors.get_line_of_scrimmage_color(play=play)
    line_of_scrimage_x = get_true_x_position(yard_position=play.location, is_home=play.posHome)
    draw = draw_vertical_line(draw=draw, x=line_of_scrimage_x, y1=0, y2=static.field_height,
                              color=line_color, thickness=FIELD_LINE_THICKNESS)
    return draw


def play_is_turnover(play: PlaySummary) -> bool:
    return play.actualResult in [Result.TURNOVER, Result.TURNOVER_TOUCHDOWN, Result.TURNOVER_PAT, Result.SAFETY]


def play_is_to_endzone(play: PlaySummary) -> bool:
    if play.actualResult in [Result.TOUCHDOWN, Result.TWO_POINT, Result.TURNOVER_TOUCHDOWN, Result.TURNOVER_PAT,
                             Result.SAFETY]:
        return True  # Some team (offense or defense) crossed a goal line somewhere

    if play.play in [Play.FIELD_GOAL, Play.PAT] and not play_is_turnover(play=play):
        return True  # A kick was attempted and didn't end in a (non-scoring) turnover

    return False


def draw_play_line(draw: ImageDraw,
                   play: PlaySummary,
                   line_y_position: int,
                   colors: GraphicColors) -> ImageDraw:
    start_yardage = int(play.location)
    play_yards = 0 if not play.yards else int(play.yards)

    if play_is_to_endzone(play=play):
        # Just draw a line off the edge of the screen to ensure it reaches the back of the endzone
        play_yards = static.field_width + 1

    if play_is_turnover(play=play):
        play_yards *= -1  # Draw turnovers as negative yardage

    end_yardage = start_yardage + play_yards

    start_x = get_true_x_position(yard_position=start_yardage, is_home=play.posHome)
    end_x = get_true_x_position(yard_position=end_yardage, is_home=play.posHome)

    # if no gain, draw at least a single pixel
    if start_x == end_x:
        end_x += 1

    play_color = colors.get_play_color(play=play)

    draw = draw_horizontal_line(draw=draw, x1=start_x, x2=end_x, y=line_y_position, color=play_color,
                                thickness=PLAY_LINE_THICKNESS)

    return draw


def makeField(plays: List[PlaySummary],
              colors: GraphicColors = None) -> Image:
    """
    Create a field image with the given plays

    :param plays: List of plays to display on the field
    :param colors: Optional, override default colors for graphic
    :return: Image of the field with the plays drawn
    """
    if not colors:
        colors = GraphicColors(
            home_team_color=DEFAULT_ENDZONE_COLOR,
            away_team_color=DEFAULT_ENDZONE_COLOR,
            field_color=DEFAULT_FIELD_COLOR,
            field_line_color=DEFAULT_FIELD_LINE_COLOR,
            endzone_border_color=DEFAULT_ENDZONE_BORDER_COLOR,
            pass_color=DEFAULT_PASS_COLOR,
            run_color=DEFAULT_RUN_COLOR,
            kick_made_color=DEFAULT_KICK_MADE_COLOR,
            kick_miss_color=DEFAULT_KICK_MISS_COLOR,
            turnover_color=DEFAULT_TURNOVER_COLOR,
            alt_color=DEFAULT_ALT_PLAY_COLOR
        )

    field = Image.new(mode='RGB', size=(static.field_width, static.field_height), color=colors.field_color)
    draw = ImageDraw.Draw(field)

    # Draw endzones
    draw = fill_in_box(draw=draw, x1=LEFT_ENDZONE_START_X, x2=FIELD_START_X, y1=0, y2=static.field_height,
                       color=colors.home_team_color)
    draw = fill_in_box(draw=draw, x1=FIELD_END_X, x2=RIGHT_ENDZONE_END_X, y1=0, y2=static.field_height,
                       color=colors.away_team_color)

    # Draw main field
    draw = fill_in_box(draw=draw, x1=FIELD_END_X, x2=FIELD_END_X, y1=0, y2=static.field_height,
                       color=colors.field_color)

    # Draw yard lines
    for fifth_yard_line in range(FIELD_START_X, FIELD_END_X + 1, FIELD_LINE_INTERVAL_X):  # +1 to be inclusive
        # Use DEFAULT_ENDZONE_BORDER_COLOR for the endzone lines, otherwise use field_line_color for 5-yard lines
        color = colors.endzone_border_color \
            if (fifth_yard_line == FIELD_START_X or fifth_yard_line == FIELD_END_X) else colors.field_line_color
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
            draw = draw_line_of_scrimmage(draw=draw, play=play, colors=colors)
            line_of_scrimmage_drawn = True

        # Draw the play line for a yardage-change play (including made field goal)
        draw = draw_play_line(draw=draw,
                              play=play,
                              line_y_position=play_y_position,
                              colors=colors)
        play_y_position += SPACING_BETWEEN_PLAY_LINES

    return field
