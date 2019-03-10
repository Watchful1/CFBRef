import cloudinary
import traceback
import logging.handlers
from cloudinary.uploader import upload
from io import BytesIO
from PIL import Image, ImageDraw

import classes
import globals
from classes import Play

log = logging.getLogger("bot")


adj = int(globals.field_width / 120)

run_color = "red"
pass_color = "blue"


def init():
	cloudinary.config(
		cloud_name=globals.CLOUDINARY_BUCKET,
		api_key=globals.CLOUDINARY_KEY,
		api_secret=globals.CLOUDINARY_SECRET
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


def makeField(plays):
	field = Image.new(mode='RGB', size=(globals.field_width, globals.field_height), color="green")
	draw = ImageDraw.Draw(field)
	x_start = 10 * adj
	x_end = 110 * adj
	x_step = 5 * adj
	for x in range(0, x_start):
		line = ((x, 0), (x, field.height))
		draw.line(line, fill="lightgrey")
	for x in range(x_end + 1, field.width):
		line = ((x, 0), (x, field.height))
		draw.line(line, fill="lightgrey")
	for x in range(x_start, x_end + 1, x_step):
		line = ((x, 0), (x, field.height))
		if x == 10 * adj or x == 110 * adj:
			draw.line(line, fill="black")
		else:
			draw.line(line, fill="grey")

	line_y_position = 5
	start_line_drawn = False
	for play in plays:
		if not start_line_drawn and play.play in classes.movementPlays:
			if play.posHome:  # home goes left to right, away goes right to left
				line = (((play.location + 10) * adj, 0), ((play.location + 10) * adj, field.height))
			else:
				line = ((((100 - play.location) + 10) * adj, 0), (((100 - play.location) + 10) * adj, field.height))
			draw.line(line, fill="white")
			start_line_drawn = True

		if play.yards is None:  # drive is over, need to handle FG, TOUCHDOWNS, and KICKOFFS eventually. Currently showing only non-scoring runs and passes
			continue
		else:
			if line_y_position > field.height:
				line_y_position = 5
			if play.posHome:  # home team has it, going left to right
				line = (((play.location + play.yards + 10) * adj, line_y_position),
							((play.location + 10) * adj, line_y_position + 1))
			else:  # away team has it, going right to left
				line = (((((100 - play.location) - play.yards) + 10) * adj, line_y_position),
							(((100 - play.location) + 10) * adj, line_y_position + 1))
			if play.play == Play.RUN:
				draw.rectangle(line, fill=run_color)
			elif play.play == Play.PASS:
				draw.rectangle(line, fill=pass_color)
			line_y_position = line_y_position + 10
	return field
