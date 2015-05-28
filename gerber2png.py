#!/usr/bin/env python3

import os
import sys
from PIL import Image, ImageDraw, PngImagePlugin
import math

BORDER_MM = 0.5
PPI = 1000
STEP = 1

print("\nGerber2PNG.py ver. 20 may 2015\n")

current_dir = os.getcwd()

if len(sys.argv) > 1:
	project_name = sys.argv[1]
else:
	print("ERR: project name missing!")
	exit()	

#print("Searching directory:", current_dir)
print("Project name:", project_name)

#prefix = current_dir + "/" + project_name
prefix = project_name

gerberfiles = []
gerberfiles.append( prefix + "-Edge_Cuts.gbr" )
gerberfiles.append( prefix + "-B_Cu.gbl" )
gerberfiles.append( prefix + "-F_Cu.gtl" )
gerberfiles = list(filter(lambda f: os.path.isfile(f), gerberfiles))

drillfiles = []
drillfiles.append( prefix+"-NPTH.drl" )
drillfiles.append( prefix+".drl" )
drillfiles = list(filter(lambda f: os.path.isfile(f), drillfiles))

for gerberfile in gerberfiles:
	print("GERBER FOUND:",gerberfile)

for drillfile in drillfiles:
	print("DRILL FOUND:",drillfile)

print()


#===================================================================================


def get_distance(p1, p2):
	maxx = max( p1[0], p2[0])
	minx = min( p1[0], p2[0])
	maxy = max(p1[1], p2[1])
	miny = min(p1[1], p2[1])
	return math.sqrt( math.pow( maxx-minx,2) + math.pow( maxy-miny,2) )

PI = math.pi
HALF_PI = math.pi / 2.0
DOUBLE_PI = math.pi * 2.0
	
def get_angle( x1, y1, x2, y2):
	res = math.atan2(y1-y2, x2-x1)
	if res < 0:
		return DOUBLE_PI + res
	else:
		return res

def take_step( x, y, angle, step):
	return ( x + math.sin(angle+HALF_PI)*step, y+math.cos(angle+HALF_PI)*step )

def calc_step( begin, end, step):
	angle = get_angle(begin[0], begin[1], end[0], end[1])
	return take_step(begin[0], begin[1], angle, step)


class Circle:
	def __init__(self, x, y, diameter, inverted=False):
		self.x = x
		self.y = y
		self.diameter = diameter
		self.inverted = inverted


class Rect:
	def __init__(self, x, y, width, height):
		self.x = x
		self.y = y
		self.width = width
		self.height = height


#===================================================================================


class Aperture:
	def __init__(self, type, modifiers, ppi):
		self.type = type
		self.modifiers = modifiers
		self.ppi = ppi

	def draw(self, x, y, inverted=False):
		primitives = []

		if self.type == "C": # draw circle
			diameter =  int(round(self.modifiers[0] * self.ppi))
			xx = x - int(round(diameter/2.0))
			yy = y - int(round(diameter/2.0))
			primitives.append( Circle( xx, yy, diameter, inverted ))

		elif self.type == "R": # draw rectangle
			width = int(round( self.modifiers[0] * self.ppi))
			height = int(round( self.modifiers[1] * self.ppi))
			xx = x - int(round(width/2.0))
			yy = y - int(round(height/2.0))
			primitives.append( Rect( xx, yy, width, height ))

		elif self.type == "O": # draw oval
			w = self.modifiers[0] * self.ppi
			h = self.modifiers[1] * self.ppi
			
			upright = True
			if w > h:
				upright = False
			
			if upright:
				diameter = int(round(w))
				half_diameter = int(round(w/2.0))
				height = int(round(h))
				half_height = int(round(h/2.0))
				
				primitives.append( Circle( x-half_diameter, y-half_height, diameter ))
				primitives.append( Circle( x-half_diameter, y+half_height-diameter, diameter ))
				primitives.append( Circle( x-half_diameter, y-half_diameter, diameter ))
			else:
				diameter = int(round(h))
				half_diameter = int(round(h/2.0))
				width = int(round(w))
				half_width = int(round(w/2.0))
			
				primitives.append( Circle( x-half_width, y-half_diameter, diameter ))
				primitives.append( Circle( x+half_width-diameter, y-half_diameter, diameter ))
				primitives.append( Circle( x-half_diameter, y-half_diameter, diameter ))
		
		return primitives


#===================================================================================


class GerberData:
	def __init__(self, ppi, step):
		self.ppi = ppi
		self.step = step
		self.apertures = {}
		self.aperture = None
		self.scale = 1
		self.last_point = ( 0, 0 )
		self.primitives = []
		self.single_quadrant = False
		self.multi_quadrant = False
		self.arc_count = 0


	def add_aperture(self, line):
		s = line[3:]			# strip the %AD
		n = int( s[1:3] )		# get the aperture number
		type = s[3:4]			# get the type
 		# extract modifiers
		mods = s[s.find(",")+1: s.find("*")]
		modifiers = []

		while len(mods) > 0:
			xpos = mods.find("X")
			if xpos != -1:
				modifiers.append( float( mods[0:xpos] ))
				mods = mods[xpos+1:]
			else:
				modifiers.append( float( mods ))
				mods = ""

		print("Aperture definition",n,type,modifiers) 		
		self.apertures[n] = Aperture(type, modifiers, self.ppi)

	def select_aperture(self, line):
		s = line[3:] 		# strip the G54
		n = int( s[1:3] )	# get the aperture number
		print("Selecting aperture",n)
		self.aperture = self.apertures[n]

	def format_number(self,s):
		# add leading zeroes
		while len(s) < 7:
			s = "0"+s
		# add decimal point
		s = s[0: 3] + "." + s[3:]
		return float(s)


	def parse_value(self, s):
		negative = False
		# strip minus signs
		if s.startswith("-"):
			s = s[1:]
			negative = True
		# add leading zeroes
		while len(s) < 7:
			s = "0"+s
		# add decimal point
		s = s[0: 3] + "." + s[3:]
				
		i = int( round( float(s) * self.ppi))
		if negative:
			i = i*-1
		return i
	
	def draw(self, line):
		xpos = line.find("X")
		ypos = line.find("Y")
		dpos = line.find("D")
		xstr = line[xpos+1: ypos]
		ystr = line[ypos+1: dpos]

		x = int(round( self.format_number(xstr) * self.ppi ))
		y = int(round( self.format_number(ystr) * self.ppi ))

		# move with shutter OPEN
		if line.endswith("D01*"):
 			# make a path from lastPoint to x,y
			while get_distance(self.last_point, (x, y)) > self.step:
				next_point = calc_step(self.last_point, (x, y), self.step)
				xx = int(round(next_point[0]))
				yy = int(round(next_point[1]))
				self.primitives.extend(self.aperture.draw(xx, yy))
				self.last_point = next_point

		elif line.endswith("D02*"): 	# move with shutter CLOSED
			self.last_point = ( x, y )

		elif line.endswith("D03*"): # flash
			self.primitives.extend(self.aperture.draw(x, y))
			self.last_point = ( x, y )


	def draw_arc(self, line, clockwise):
		xpos = line.find("X")
		ypos = line.find("Y")
		ipos = line.find("I")
		jpos = line.find("J")
		dpos = line.find("D")

		xstr = line[xpos+1: ypos]
		ystr = line[ypos+1: ipos]
		istr = line[ipos+1: jpos]
		jstr = line[jpos+1: dpos]

		x = self.parse_value(xstr)
		y = self.parse_value(ystr)
		i = self.parse_value(istr)
		j = self.parse_value(jstr)
		
		#print("Arc a:", xstr, ", ", ystr, ", ", istr, ", ", jstr)
		#print("Arc b:", x, ", ", y, ", ", i, ", ", j)

		centerx = int(self.last_point[0] + i)
		centery = int(self.last_point[1] + j)
		
		radius = get_distance(self.last_point, (centerx, centery))
		end_angle = get_angle(centerx, centery, self.last_point[0], self.last_point[1])
		start_angle = get_angle(centerx, centery, x, y)
		arc_resolution = 0.00175

#		if not clockwise:
		if start_angle > end_angle:
			end_angle += DOUBLE_PI

		
		print("Circle at: [", centerx, ", ", centery, "] Radius:", radius)
		print("start Angle: ", start_angle, math.degrees(start_angle))
		print("end Angle: ", end_angle, math.degrees(end_angle))
		


		# The parametric equation for a circle is
		# x = cx + r * cos(a) 
		# y = cy + r * sin(a) 
		# Where r is the radius, cx,cy the origin, and a the angle from 0..2PI radians or 0..360 degrees.


		if line.endswith("D01*"): # move with shutter OPEN
			# make a path from lastPoint to x,y
			#angle = DOUBLE_PI
			angle = start_angle
#			if angle == 0: 
#				angle = DOUBLE_PI
			while angle < end_angle:
				xx = int( round(centerx + radius * math.cos(-angle)))
				yy = int( round(centery + radius * math.sin(-angle)))

				self.primitives.extend(self.aperture.draw(xx, yy))
				self.last_point = (xx, yy)
				angle += arc_resolution


	def parse_line(self, line):
		if line.startswith("G04"):
#			print("ignoring comment")
			pass
		elif line.startswith("%MOIN*%"):
			print("Dimensions in Inches")
			self.scale = 25.4;
		elif line.startswith("%MOMM*%"):
			print("Dimensions in Millimeters")
			self.scale = 1;
		elif line.startswith("%FS"):
#			print("File is in the correct format")
			if not line == "%FSLAX34Y34*%":
				print("wrong format definition! STOPPING...")
				exit()
		elif line.startswith("%AD"):
			#print("got aperture definition!")
			self.add_aperture(line)
		elif line.startswith("G54"):
			#print("Select aperture")
			self.select_aperture(line)
		elif line.startswith("M02"):
			print("STOP")
			#return true;
		elif line.startswith("X"):
			self.draw(line)
		elif line.startswith("G74"):
			#print("Selecting Single quadrant mode")
			self.single_quadrant = True
			self.multi_quadrant = False
		elif line.startswith("G75"):
			#print("Selecting Multi quadrant mode")
			self.single_quadrant = False
			self.multi_quadrant = True
		elif line.startswith("G02"): #clockwise arc
			self.draw_arc(line, True)
		elif line.startswith("G03"): #counter clockwise arc
#			self.arc_count += 1
#			if self.arc_count == 4: # or self.arc_count == 2:
			self.draw_arc(line, False)
		else:
			print("Ignoring line:",line)


#===================================================================================


class DrillData:
	def __init__(self, ppi):
		self.ppi = ppi
		self.apertures = {}
		self.scale = 1
		self.primitives = []

	def add_tool(self, line):
		s = line[1:] # strip the T
		# get the tool number
		cpos = s.find("C")
		n = int(s[0:cpos])
		# extract modifiers
		modifiers = []
		mods = s[cpos+1:]
		
		while len(mods) > 0:
			xpos = mods.find("X")
			if xpos != -1:
				modifiers.append( float( mods[0, xpos] ))
				mods = mods[xpos+1:]
			else:
				modifiers.append( float(mods))
				mods = ""
		
		print("Drill definition",n,modifiers) 		
		self.apertures[n] = Aperture("C", modifiers, self.ppi)

	def select_tool(self, line):
		s = line[1:] 	# strip the T
		n = int(s)		# get the tool number
		print("Selecting drill",n)
		self.aperture = self.apertures[n]

	def drill(self, line):
		xpos = line.find("X")
		ypos = line.find("Y")
		xstr = line[xpos+1: ypos]
		ystr = line[ypos+1:]
		
		if ystr.startswith("-"): 
			ystr = ystr[1:]
		
		# add leading zeroes
		while len(xstr) < 6:
			xstr = "0"+xstr
		while len(ystr) < 6:
			ystr = "0"+ystr

		# add decimal point
		xstr = xstr[0:2] + "." + xstr[2:]
		ystr = ystr[0:2] + "." + ystr[2:]
				
		x = int(round( float(xstr) * self.ppi))
		y = int(round( float(ystr) * self.ppi))
				
		y = math.fabs(y) # invert
		
		self.primitives.extend(self.aperture.draw(x, y, True))
		self.last_point = (x, y)

	def parse_line(self, line):
		pass

		if line.startswith("T"):
			if line.find("C") != -1:
				#print("got tool definition!")
				self.add_tool(line)
			else:
				#print("got tool change!")
				if not line == "T0":
					self.select_tool(line)
		elif line.startswith("M30"):
			print("STOP")
		elif line.startswith("X"):
			self.drill(line)
		else:
			print("Ignoring line:",line)


#===================================================================================


def process_gerber(filename, ppi, step):
	print("Processing Gerber:",filename)
	gerber_data = GerberData(ppi, step)
	with open(filename, 'r') as f:
		for line in f:
			line = line.rstrip('\n')
			gerber_data.parse_line(line)
	f.closed
	print("# of primitives:",len(gerber_data.primitives),"\n")
	return gerber_data.primitives


def process_drill(filename, ppi):
	print("Processing Drillfile:",filename)
	drill_data = DrillData(ppi)
	with open(filename, 'r') as f:
		for line in f:
			line = line.rstrip('\n')
			drill_data.parse_line(line)
	f.closed
	print("# of primitives:",len(drill_data.primitives),"\n")
	return drill_data.primitives


def get_max_dimensions(primitives):
	highX = 0;
	highY = 0;

	for p in primitives:
		if type(p) == Circle:
			xmax = p.x+p.diameter
			if xmax > highX:
				highX = xmax
			ymax = p.y+p.diameter
			if ymax > highY:
				highY = ymax
		elif type(p) == Rect:
			xmax = p.x+p.width
			if xmax > highX:
				highX = xmax
			ymax = p.y+p.height
			if ymax > highY:
				highY = ymax

	return (highX, highY)


def create_image(filename, dimensions, ppi, border_mm, primitives, inverted=False):
	border_pixels = int(round(border_mm/25.4*ppi))
	w = dimensions[0] + 2 * border_pixels
	h = dimensions[1] + 2 * border_pixels
	#print("dimensions:",w,h)

	im = Image.new("RGB", (w,h))
	draw = ImageDraw.Draw(im)
	black = 0x000000
	white = 0xFFFFFF
	fill = white

	if inverted:
		draw.rectangle( [0, 0, w, h], white)
		fill = black

	print("Generating image...")

	for p in primitives:
		if type(p) == Circle:
			x = p.x + border_pixels
			y = p.y + border_pixels
			if p.inverted or inverted:
				fill = black
			else: 
				fill = white
			draw.ellipse( [ x, y, x+p.diameter, y+p.diameter], fill)
		elif type(p) == Rect:
			x = p.x + border_pixels
			y = p.y + border_pixels
			draw.rectangle( [x, y, x+p.width, y+p.height], fill)

	del draw
	print("Writing", filename)
	im.save(filename, "PNG", dpi=(ppi,ppi))


#===================================================================================


edge_primitives = process_gerber(gerberfiles[0], PPI, STEP)
dimensions = get_max_dimensions(edge_primitives)

trace_primitives = process_gerber(gerberfiles[1], PPI, STEP)
drill_primitives = process_drill(drillfiles[0], PPI)

traces = []
traces.extend(trace_primitives)
traces.extend(drill_primitives)
create_image(prefix+"_MILL-TRACES.png", dimensions, PPI, BORDER_MM, traces)

cutouts = []
cutouts.extend(edge_primitives)
cutouts.extend(drill_primitives)
create_image(prefix+"_MILL-CUTOUT.png", dimensions, PPI, BORDER_MM, cutouts, True)
