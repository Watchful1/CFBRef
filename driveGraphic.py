from PIL import Image, ImageColor, ImageDraw
from pathlib import Path

height = 53
width = 120
adj = width/120

run_color = "red"
pass_color = "blue"

driveEnders = [Result.TURNOVER, Result.TOUCHDOWN, Result.TURNOVER_TOUCHDOWN, Result.FIELD_GOAL, Result.PUNT]

def makeNewField(homeHasPossession,startingLocation):
    field = Image.new(mode='RGB', size=(width,height), color="green")
    x_start = 10*adj
    x_end = 110*adj
    x_step = 5*adj
    for x in range(0,x_start):
        line = ((x,0),(x,field.height))
        draw.line(line,fill="lightgrey")
    for x in range(x_end+1,field.width):
        line = ((x,0),(x,field.height))
        draw.line(line,fill="lightgrey")
    for x in range(x_start,x_end+1,x_step):
        line = ((x, 0),(x,field.height))
        if x == 10*adj or x == 110*adj:
            draw.line(line,fill="black")
        else:
            draw.line(line,fill="grey")
    #only time file should not exist is when drive first starts. Adds initial LoS here.
    if homeHasPossession: #home goes left to right, away goes right to left
         line = (((startingLocation+10)*adj,0),((startingLocation+10)*adj,field.height))
    else:
         line = ((((100-startingLocation)+10)*adj,0),(((100-startingLocation)+10)*adj,field.height))
    draw.line(line,fill="white")
    return field
    
def addToField(List_of_Plays):
    #currently, keeping track of play results
    #places starting line of scrimmage for drive, and then lines for each play
    field = ""
    if Path("field_ID.png").is_file():
        field = Image.open('field_ID.png')
    else:
        field = makeNewField(List_of_Plays[0].posHome,List_of_Plays[0].location)
        field.save('field_ID.png',"PNG")
    line_y_position = 5
    draw = ImageDraw.Draw(field)
    line = ((0,0),(0,0))
    for play in List_of_Plays:
        if play.result in driveEnders: #drive is over, need to handle FG, TOUCHDOWNS, and KICKOFFS eventually. Currently showing only non-scoring runs and passes
            field.save('field_ID.png',"PNG")
            break
        else:
            if line_y_position > field.height:
                line_y_position = 5
            if play.posHome == True: #home team has it, going left to right
                line = ((play.yards+10)*adj,line_y_position),((play.location+10)*adj,line_y_position))
            else: #away team has it, going right to left
                line = ((100-play.yards+10)*adj,line_y_position),((100-play.location+10)*adj,line_y_position))
            if play.play == RUN:
                draw.line(line,color=run_color)
            if play.play == PASS:
                draw.line(line,color=pass_color)
            line_y_position = line_y_position + 5
    field.save('field_ID.png',"PNG")
