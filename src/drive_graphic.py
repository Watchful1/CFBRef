from PIL import Image, ImageColor, ImageDraw

import classes
from classes import Play

height = 53
width = 120
adj = int(width / 120)

run_color = "red"
pass_color = "blue"


def makeField(fieldFileName, plays):
	field = Image.new(mode='RGB', size=(width, height), color="green")
	draw = ImageDraw.Draw(field)
	line = ((0, 0), (0, 0))
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

	if plays[0].posHome:  # home goes left to right, away goes right to left
		line = (((plays[0].location + 10) * adj, 0), ((plays[0].location + 10) * adj, field.height))
	else:
		line = ((((100 - plays[0].location) + 10) * adj, 0), (((100 - plays[0].location) + 10) * adj, field.height))
	draw.line(line, fill="white")

	line_y_position = 5
	for play in plays:
		if play.result in classes.driveEnders or play.yards is None:  # drive is over, need to handle FG, TOUCHDOWNS, and KICKOFFS eventually. Currently showing only non-scoring runs and passes
			continue
		else:
			print("Drawing play: "+str(play))
			if line_y_position > field.height:
				line_y_position = 5
			if play.posHome:  # home team has it, going left to right
				line = (((play.yards + 10) * adj, line_y_position), ((play.location + 10) * adj, line_y_position))
			else:  # away team has it, going right to left
				line = (
				((((100 - play.location) - play.yards) + 10) * adj, line_y_position), (((100 - play.location) + 10) * adj, line_y_position))
			print(str(line) + " : " + str(line_y_position))
			if play.play == Play.RUN:
				draw.line(line, fill=run_color)
			elif play.play == Play.PASS:
				draw.line(line, fill=pass_color)
			line_y_position = line_y_position + 5
	field.save(fieldFileName, "PNG")
