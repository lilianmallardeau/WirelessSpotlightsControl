"""
Commons parameters and functions to client and server
"""

# ------------------------ LIBRAIRIES IMPORT ------------------------ #
import sys
pythonv = sys.version_info[0]

from threading import Thread, RLock
from queue import Queue
import socket
import pickle
import time
import json

# --------------------------- PARAMETERS ---------------------------- #
# Common to client and server parameters
EOC = "@@EOC#" # Str used for commands separation between client and server
ParamsSep = "@@|#" # Str used for command parameters separation between client and server
exit_msg = "Bye :)"
# DMX Protocol standard parameters
minChannelValue = 0
maxChannelValue = 255
minChannel = 1
maxChannel = 512

# ---------------------- FUNCTIONS AND CLASSES ---------------------- #
def get_user_input():
	if pythonv < 3 : return raw_input()
	else: return input()
def getinput(*args, **kwargs):
	global pythonv
	if not "sep" in kwargs.keys() : kwargs["sep"] = " "
	if not "end" in kwargs.keys() : kwargs["end"] = ""
	if "choices" in kwargs.keys():
		choices = kwargs["choices"]
		rep = str()
		if "casesensitive" in kwargs.keys() and kwargs["casesensitive"] == True:
			while not rep in choices:
				print(*args, sep=kwargs["sep"], end=kwargs["end"])
				rep = get_user_input()
			return rep
		else:
			while not rep.lower() in [x.lower() for x in choices]:
				print(*args, sep=kwargs["sep"], end=kwargs["end"])
				rep = get_user_input()
			return rep
	else:
		print(*args, sep=kwargs["sep"], end=kwargs["end"])
		return get_user_input()
def is_numeric(n):
	try:
		if type(n) is str: n = n.replace(",", ".")
		float(n)
		return True
	except Exception as e:
		return False
def to_float(n):
	if not is_numeric(n): return None
	if type(n) is str: n = n.replace(",", ".")
	return float(n)
def is_int(n):
	try:
		if not is_numeric(n): return False
		n = to_float(n)
		if n%1 == 0: return True
		else: return False
	except Exception as e:
		return False
def to_int(n):
	if not is_numeric(n): return None
	n = to_float(n)
	return int(n)
def getintinput(*args, **kwargs):
	ui = str()
	if "min" in kwargs.keys(): min = kwargs["min"]
	else : min = None
	if "max" in kwargs.keys(): max = kwargs["max"]
	else : max = None
	done = False
	while not done:
		ui = getinput(*args, **kwargs)
		if is_int(ui):
			done = True
			ui = int(ui)
			if min is not None:
				if ui >= min: done = done and True
				else : done = False
			else: done = done and True
			if max is not None:
				if ui <= max: done = done and True
				else: done = False
			else: done = done and True
	return int(ui)
def is_dmxchannel(channel):
	if is_int(channel):
		channel = to_int(channel)
		if channel >= minChannel and channel <= maxChannel: return True
		else: return False
	else:
		return False 
def is_dmxvalue(value):
	if is_int(value):
		value = to_int(value)
		if value >= minChannelValue and value <= maxChannelValue: return True
		else: return False
	else:
		return False
def dmxvalue(value):
	if is_numeric(value):
		value = to_float(value)
		if value < minChannelValue:
			return minChannelValue
		if value > maxChannelValue:
			return maxChannelValue
		return to_int(value)
	else: return None
def get_user_fxtid_input(before="", end=" ", **kwargs):
	if not "min" in kwargs.keys(): kwargs["min"] = 0
	if "sep" in kwargs.keys(): del kwargs["sep"]
	return getintinput(before, "Enter id:", sep="", end=end, **kwargs)
def get_user_fxtuniv_input(before="", end=" ", **kwargs):
	if not "min" in kwargs.keys(): kwargs["min"] = 0
	if "sep" in kwargs.keys(): del kwargs["sep"]
	return getintinput(before, "Universe:", sep="", end=end, **kwargs)
def get_user_fxtaddr_input(before="", end=" ", **kwargs):
	if "min" in kwargs.keys(): del kwargs["min"]
	if "max" in kwargs.keys(): del kwargs["max"]
	if "sep" in kwargs.keys(): del kwargs["sep"]
	return getintinput(before, "DMX Address:", sep="", end=end, min=minChannel, max=maxChannel, **kwargs)
def copy(object):
	if type(object) is str: return str(object)
	if type(object) is int: return int(object)
	if type(object) is float: return float(object)
	if type(object) is list: return list(object)
	if type(object) is dict: return dict(object)
	return object
def convert_container_elements(container_object):
	container = copy(container_object)
	if type(container) is list: var = range(len(container))
	elif type(container) is dict: var = container.keys()
	else: return None
	for x in var:
		if type(container[x]) is list or type(container[x]) is dict:
			container[x] = convert_container_elements(container[x])
		elif type(container[x]) is str:
			if is_numeric(container[x]):
				if is_int(container[x]):
					container[x] = to_int(container[x])
				else: container[x] = to_float(container[x])
	if type(container) is dict:
		container_copy = copy(container)
		for x in container.keys():
			m = False
			if type(x) is list or type(x) is dict:
				new_x = convert_container_elements(x)
			elif type(x) is str:
				if is_numeric(x):
					if is_int(x):
						new_x = to_int(x)
					else: new_x = to_float(x)
					m = True
			if m:
				container_copy[new_x] = container[x]
				del container_copy[x]
		return container_copy
	else: return container
def create_fixture(before="", end=" ", indent=""):
	name = getinput(before, "Name:", sep="", end=end)
	brand = getinput(before, "Brand:", sep="", end=end)
	fxt_type = getinput(before, "Type:", sep="", end=end)
	channels_n = getintinput(before, "Numbers of DMX channels:", sep="", end=end, min=1, max=maxChannel)
	channels = {}
	for x in range(1, channels_n+1):
		print("Channel", x)
		channels[x] = {}
		channels[x]["name"] = getinput(before, indent, "Channel name :", sep=" ", end=end)
		channels[x]["default"] = getintinput(before, indent, "Default value :", sep=" ", end=end, min=minChannelValue, max=maxChannelValue)
		groups_n = getintinput(before, indent, "Number of values groups :", sep=" ", end=end, min=0)
		channels[x]["groups"] = {}
		for y in range(1,groups_n+1):
			channels[x]["groups"][y] = {}
			channels[x]["groups"][y]["start"] = getintinput(before, indent*2, "Start value :", sep="", end=end, min=minChannelValue, max=maxChannelValue)
			channels[x]["groups"][y]["stop"] = getintinput(before, indent*2, "Stop value :", sep="", end=end, min=minChannelValue, max=maxChannelValue)
			channels[x]["groups"][y]["desc"] = getinput(before, indent*2, "Description :", sep="", end="\n")
	return {"name":name, "brand":brand, "type":fxt_type, "channels":channels}