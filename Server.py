# OlaThreaded : https://github.com/s-light/OLA_channel_mapper/blob/master/olathreaded.py

"""
/!\ This server works with the Open Lighting Architecture project (OLA).
https://www.openlighting.org/ola/
To make it works, first you've to install the OLA server and patch at least one universe (no. 1):

sudo apt-get update
sudo apt-get install ola 			# to install the OLA server
sudo apt-get install ola-python 	# to install libola, the library used by this server to communicate with OLA

sudo /etc/init.d/olad start			# to start the ola deamon (olad)

Then you've to patch an universe. You can do it with command line, see doc here:
https://www.openlighting.org/ola/getting-started/using-ola/
or graphically, here:
http://localhost:9090/

To use LibOla with Python 3, you've to do that before:
sudo cp -r /usr/lib/python2.7/dist-packages/ola /usr/lib/python3/dist-packages/ola
sudo apt-get install python3-pip # Install python3 package manager
sudo -H pip3 install protobuf
(doc here: https://groups.google.com/forum/#!topic/open-lighting/7TuvU0T1CAo)

If you want to run this server with Python 2, you'll need the future librairie :
sudo -H pip install future
# sudo apt-get install python-future
# sudo apt-get install python3-future

"""

# ------------------------ LIBRAIRIES IMPORT ------------------------ #

from __future__ import print_function, absolute_import, division, unicode_literals

from common import *

# Future for interoperability with Python 2 and Python 3
if pythonv < 3:
	from future import standard_library
	standard_library.install_aliases()
	from builtins import *
	from future.builtins import next
	from future.builtins import object
	#import configparser
if pythonv >= 3:
	sys.path.append('/usr/lib/python3/dist-packages/ola')
from ola.ClientWrapper import ClientWrapper # LibOla
import os
import array

# ------------------------ SERVER PARAMETERS ------------------------ #
port = 6969 # Port listened by server
passwd = "pwd" # Password required for client connection /!\ Warning : must be 2048 char max
nUniv = 1 # Number of universes to patch to OLA
univ_ids = [i for i in range(nUniv)]
server_autostart = True # Launch server thread at startup to allow clients connections
patchfile = "patch_sav.patch" # File in which is saved patch configuration
fxt_library_folder = "fixture_library" # Folder in which to look and save fixtures files
save_patch_on_shutdown = True # Save patch configuration to patchfile when shuting down
vbLevel = 2 # Verbose Level, from 0 to 2. Usefull for debug # useless for now

# ---------------------- FUNCTIONS AND CLASSES ---------------------- #
def shutdown():
	global server, patch
	server.stoplistening()
	server.reset()
	stop_updating_all_universes()
	if save_patch_on_shutdown :
		patch.save()
		print("Patch saved.")
	exit(exit_msg)

class Universe:
	"""docstring for Universe"""
	def __init__(self, n, name=None, dmxdata=None, defaultDmxValue=minChannelValue):
		self.n = n
		if name is None: self.name = "Universe " + str(n)
		else : self.name = name
		self.defaultDmxValue = defaultDmxValue
		if dmxdata is None: self.dmxdata = [self.defaultDmxValue for x in range(512)]
		else : self.dmxdata = dmxdata
		self.updating = True
		self.last_change = time.time()
	def update_universe(self):
		global OlaClient
		OlaClient.setDmxData(self.n, self.dmxdata)
	def get_dmxdata(self):
		return self.dmxdata
	def get_value(self, channel):
		if not is_dmxchannel(channel): return None
		return self.dmxdata[to_int(channel)-1]
	def set_value(self, channel, value):
		if is_dmxchannel(channel) and is_dmxvalue(value):
			self.dmxdata[to_int(channel)-1] = dmxvalue(value)
			self.univ_updated()
			return True
		else: return False
	def set_values(self, dict_values):
		if type(dict_values) is not dict: return False
		r = list()
		for channel, value in dict_values.items():
			if is_dmxchannel(channel) and is_dmxvalue(value):
				self.dmxdata[to_int(channel)-1] = dmxvalue(value)
				r.append(True)
			else: r.append(False)
		self.univ_updated()
		return tuple(x for x in r)
	def set_allchannels(self, value):
		if not is_dmxvalue(value): return False
		self.dmxdata = [dmxvalue(value) for x in range(512)]
		self.univ_updated()
		return True
	def reset(self):
		self.dmxdata = [self.defaultDmxValue for x in range(512)]
		self.univ_updated()
	def startupdating(self):
		self.updating = True
		self.updateThread.start()
	def stopupdating(self):
		self.updating = False
	def univ_updated(self):
		self.last_change = time.time()
		if self.updating: self.updateThread.start()
	def _get_updateThread(self):
		return Thread(target=self.update_universe, args=())
	updateThread = property(_get_updateThread)
	def __getitem__(self, item):
		if not is_dmxchannel(item): return None
		return self.dmxdata[to_int(item)-1]
	def __setitem__(self, item, value):
		if is_dmxchannel(item) and is_dmxvalue(value):
			self.set_value(to_int(item), dmxvalue(value))
			return True
		else: return False

class Client(Thread):
	"""docstring for Client"""
	def __init__(self, clientsocket, ip, port, n):
		global universes
		Thread.__init__(self)
		self.clientsocket = clientsocket
		self.ip = ip
		self.port = port
		self.n = n

		self.listenActive = True
		self.sendingPatch = False
		self.sendingDmxvalues = False
		self.authentified = False

		self.listeningThread = Thread(target=self.listening, args=())
		self.sendingPatchThread = Thread(target=self.sending_patch, args=())
		self.sendingDmxvaluesThread = Thread(target=self.sending_dmxvalues, args=())
		self.sendingLock = RLock()
		self.patchLastUpdated = 0
		self.univsLastUpdated = {}
		for univ in universes.values():
			self.univsLastUpdated[univ.n] = 0
	def run(self):
		print("[+] New connection from ", self.ip, ":", self.port, ", client ", self.n, sep="", end="\n")
		self.listeningThread.start()
	def listening(self):
		while self.listenActive:
			current_command = str()
			while not current_command.endswith(EOC):
				current_command += self.clientsocket.recv(1).decode()
			self.commandManager(current_command[:-len(EOC)])
	def send(self, command):
		if not type(command) is str: return False
		sent = 0
		with self.sendingLock:
			while sent < len(command):
				sent += self.clientsocket.send(command[-(len(command)-sent):].encode())
		return True
	def sending_patch(self):
		global patch
		while self.sendingPatch and self.authentified:
			if self.patchLastUpdated < patch.lastUpdated:
				self.send_command("patch", json.dumps(patch.get()))
				self.patchLastUpdated = time.time()
	def sending_dmxvalues(self):
		global universes
		while self.sendingDmxvalues and self.authentified:
			if not len(universes) == len(self.univsLastUpdated):
				self.univsLastUpdated = [0 for i in range(len(universes))]
			for univ in universes.values():
				if not self.sendingDmxvalues and self.authentified: return
				if self.univsLastUpdated[univ.n] < univ.last_change:
					self.send_command("dmxdata", univ.n, json.dumps(univ.get_dmxdata()))
					self.univsLastUpdated[univ.n] = time.time()
	def commandManager(self, command):
		global universes, patch
		command = command.split(ParamsSep)
		action = str(command[0]).lower()
		if action == "authentify":
			self.authentify(command[1])
		if action == "authentified":
			if self.authentified: self.send_command("authentified")
			else: self.send_command("unauthentified")
		if action == "setdmxchannels":
			valuesArray = convert_container_elements(json.loads(command[1]))
			valuesDict = {}
			for value_array in valuesArray:
				univ = value_array[0]
				channel = value_array[1]
				value = value_array[2]
				if not univ in valuesDict.keys():
					valuesDict[univ] = {}
				valuesDict[univ][channel] = value
			for univ, values in valuesDict.items():
				return universes[univ].set_values(values)
		if action == "setdmxchannel":
			return universes[to_int(command[1])].set_value(command[2], command[3])
		if action == "setallchannels":
			return universes[to_int(command[1])].set_allchannels(command[2])
		if action == "resetuniv":
			universes[to_int(command[1])].reset()
		if action == "addfxt":
			fxt_id = command[1]
			fxt_univ = command[2]
			fxt_addr = command[3]
			if not is_int(fxt_id): return False
			if not is_int(fxt_univ): return False
			if not is_dmxchannel(fxt_addr): return False
			fxt = convert_container_elements(json.loads(command[4]))
			return patch.add_fxt(fxt, to_int(fxt_id), to_int(fxt_univ), to_int(fxt_addr))
		if action == "removefxt":
			fxt_id = command[1]
			if not is_int(fxt_id): return False
			return patch.remove_fxt(to_int(fxt_id))
		if action == "disconnect":
			self.close(False)
	def send_command(self, *args):
		args = [str(arg) for arg in args]
		command = ParamsSep.join(args) + EOC
		self.send(command)
	def authentify(self, sent_passwd):
		global passwd
		if sent_passwd == passwd :
			self.authentified = True
			self.active()
			self.send_command("authentified")
		else:
			self.authentified = False
			self.inactive()
			self.send_command("unauthentified")
	def active(self):
		self.sendingPatch = True
		self.sendingDmxvalues = True
		self.sendingPatchThread.start()
		self.sendingDmxvaluesThread.start()
	def inactive(self):
		self.sendingPatch = False
		self.sendingDmxvalues = False
	def start_listening(self):
		self.listenActive = True
		if not self.listeningThread.is_alive(): self.listeningThread.start()
	def stop_listening(self):
		self.listenActive = False
	def close(self, send=True):
		if send: self.send_command("disconnect")
		self.inactive()
		self.stop_listening()
		self.clientsocket.close()

class Server(Thread):
	"""docstring for Server"""
	def __init__(self, port, autostart=False):
		Thread.__init__(self)
		self.port = port
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		# tcpsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.clients = {}
		self.n = 0
		self.listening = True
		if autostart: self.start()
	def run(self):
		global printLock
		self.sock.bind(('', self.port))
		if self.listening :
			with printLock: print("Listening on port ", self.port, "...", sep="")
		while self.listening :
			self.sock.listen(10)
			clientsocket, (ip, port) = self.sock.accept()
			if not self.listening: return
			self.clients[self.n] = Client(clientsocket, ip, port, self.n)
			self.clients[self.n].start()
			self.n += 1
	def stoplistening(self):
		global printLock
		self.listening = False
		socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("127.0.0.1", self.port))
		with printLock: print("Server stoped.")
	def startlistening(self):
		global printLock
		self.listening = True
		self.start()
		with printLock: print("Server started.")
	def getclients(self):
		return self.clients
	def closeclient(self, n):
		self.clients[n].close()
	def closeallclients(self):
		for client in self.clients.values():
			client.close()
	def delclient(self, n):
		del self.clients[n]
	def delallclients(self):
		self.clients = {}
	def removeclient(self, n):
		""" Close connection with client n and delete it from Server().clients dictionary """
		self.closeclient(n)
		self.delclient(n)
	def removeallclients(self):
		for n in self.clients.keys():
			self.removeclient(n)
	def reset(self):
		self.closeallclients()
		self.delallclients()

class Patch():
	"""docstring for Patch"""
	def __init__(self, file, autosave=False, autoload=False): # univ
		# self.univ = univ
		self.file = file
		self.autosave = autosave
		self.patch = {}
		self.lastUpdated = time.time()
		if autoload:
			self.load()
	def get(self):
		return self.patch
	def load(self):
		if not os.path.isfile(self.file): return False
		with open(self.file, "rb") as handler :
			new_patch = pickle.Unpickler(handler).load()
			if type(new_patch) is not dict: return False
			self.patch = new_patch
			self.patch_updated()
		return True
	def save(self):
		with open(self.file, "wb") as handler :
			pickle.Pickler(handler).dump(self.patch)
			handler.flush()
	def set_autosave(self, autosave):
		self.autosave = bool(autosave)
		return True
	def reset(self):
		self.patch = {}
		self.patch_updated()
	def add_fxt(self, fxt, fxt_id, fxt_univ, fxt_addr, erase=True):
		if type(fxt) is not dict: return False
		if type(fxt_id) is not int: return False
		if type(fxt_univ) is not int: return False
		if type(fxt_addr) is not int or not is_dmxchannel(fxt_addr): return False
		if fxt_id in self.patch.keys() and not erase: return False
		self.patch[to_int(fxt_id)] = {"patch": {"univ":to_int(fxt_univ), "addr":to_int(fxt_addr)}, "fxt":fxt}
		self.patch_updated()
		return True
	def load_fxt(self, fxtfile_path, fxt_id, fxt_univ, fxt_addr, erase=False):
		if not os.path.isfile(fxtfile_path): return False
		with open(fxtfile_path, "rb") as handler :
			self.add_fxt(pickle.Unpickler(handler).load(), fxt_id, fxt_univ, fxt_addr, erase=erase)
		return True
	def create_fxt(self):
		before = ""; end = " "; indent = "----"
		fxt = create_fixture(before=before, end=end, indent=indent)
		choices = ["Y", "N"]
		if getinput("Do you want to save your fixture? [Y/N]", choices=choices, casesensitive=False).lower() == "y":
			with open(os.path.join(fxt_library_folder, fxt["brand"]+" - "+fxt["name"]+".fxt"), "wb") as handler:
				pickle.Pickler(handler).dump(fxt)
				handler.flush()
		if getinput("Do you want to patch new fixture now? [Y/N]", choices=choices, casesensitive=False).lower() == "y":
			fxt_id = get_user_fxtid_input(before=before, end=end)
			fxt_univ = get_user_fxtuniv_input(before=before, end=end)
			fxt_addr = get_user_fxtaddr_input(before=before, end=end)
			self.add_fxt(fxt, fxt_id, fxt_univ, fxt_addr)
	def copy_fxt(self, fxt_id, new_id, new_univ, new_addr, erase=False):
		if not fxt_id in self.patch.keys(): return False
		if new_id in self.patch.keys() and not erase: return False
		fxt = dict(self.patch[fxt_id]["fxt"])
		self.patch[new_id] = {"patch": {"univ": new_univ, "addr": new_addr}, "fxt": fxt}
		self.patch_updated()
		return True
	def change_fxt_id(self, fxt_id, new_id, erase=False):
		if not fxt_id in self.patch.keys(): return False
		if new_id in self.patch.keys() and not erase: return False
		fxt = dict(self.patch[fxt_id])
		self.patch[new_id] = fxt
		del self.patch[fxt_id]
		self.patch_updated()
		return True
	def change_fxt_addr(self, fxt_id, new_addr):
		if not fxt_id in self.patch.keys(): return False
		self.patch[fxt_id]["patch"]["addr"] = new_addr
		self.patch_updated()
		return True
	def remove_fxt(self, fxt_id):
		if not fxt_id in self.patch.keys(): return False
		del self.patch[fxt_id]
		self.patch_updated()
		return True
	def patch_updated(self):
		self.lastUpdated = time.time()
		if self.autosave: self.save()
	def __getitem__(self, item):
		if item in self.patch.keys():
			return self.patch[item]
		else: return None
	def __setitem__(self, item, value):
		if item in self.patch.keys(): return False
		self.patch[item] = value
		self.patch_updated()

class OlaClient():
	"""docstring for OlaClient"""
	def __init__(self, host="localhost", port=9091):
		self.host = host
		self.port = port
		self.olaWrapper = ClientWrapper()
		self.olaClient = self.olaWrapper.Client()
	def setDmxData(self, univ, dmxdata):
		dmxdata = array.array('B', dmxdata)
		self.olaClient.SendDmx(univ, dmxdata, self.DmxSent)
	def DmxSent(self, state):
		# self.olaWrapper.Stop()
		pass

def start_updating_universe(n):
	global universes
	universes[n].startupdating()
def start_updating_all_universes():
	global universes
	for n in universes.keys():
		start_updating_universe(n)
def stop_updating_universe(n):
	global universes
	universes[n].stopupdating()
def stop_updating_all_universes():
	global universes
	for n in universes.keys():
		stop_updating_universe(n)


# ------------------------- STARTING SERVER ------------------------- #
OlaClient = OlaClient()
universes = {}
currentUniv = univ_ids[0]
printLock = RLock()

patch = Patch(patchfile)
patch.load()

print("Settings universes...", end=" ")
for n in univ_ids:
	universes[n] = Universe(n)
	universes[n].startupdating()
del n
print("[Done]")

server = Server(port, autostart=server_autostart)

print("All okay.", end="\n\n")

while True:
	print("What to do ?")
	actions = []
	f = "-"; s = " "
	actions.append("Modify patch [patch]")
	actions.append("Set channel(s) value(s) [set]")
	actions.append("Change universe to handle [univ]")
	actions.append("Reset universe [reset]")
	actions.append("Show DMX channels values [dmxdata]")
	actions.append("Show clients list [clients]")
	actions.append("Remove client [disconnect]")
	actions.append("Start server [start]")
	actions.append("Stop listening [stop]")
	actions.append("Quit [q] [quit] [shutdown]")
	actions = [f+s+action for action in actions]
	with printLock:
		print(*actions, sep="\n", end="\n")
		print("Actions apply on universe", currentUniv, sep=" ", end="\n")
	c = getinput().lower()
	if c == "patch" :
		actions2 = []
		actions2.append("Print patch [print]")
		actions2.append("Create fixture [create]")
		actions2.append("Remove fixture [del]")
		actions2.append("Save patch to patchfile [save]")
		actions2.append("Load patch from patchfile [load]")
		actions2.append("Load fixture from file [loadfxt]")
		actions2.append("Reset patch [reset]")
		actions2.append("Exit patch menu [exit]")
		actions2 = [4*f+s+action for action in actions2]
		c2 = ""
		while c2 != "exit" :
			with printLock:
				print("What do you want to do ?")
				print(*actions2, sep="\n", end="\n")
			c2 = getinput().lower()
			if c2 == "print":
				print(json.dumps(patch.get(), indent=4))
			if c2 == "create" :
				patch.create_fxt()
			if c2 == "del" :
				n = getintinput("Id of the fixture you want to remove :", end=" ")
				patch.remove_fxt(n)
			if c2 == "save" :
				patch.save()
			if c2 == "load" :
				patch.load()
			if c2 == "loadfxt" :
				before = ""; end = " ";
				fxt_filepath = getinput(before, "File path:", sep="", end=end)
				fxt_id = get_user_fxtid_input(before=before, end=end)
				fxt_univ = get_user_fxtuniv_input(before=before, end=end)
				fxt_addr = get_user_fxtaddr_input(before=before, end=end)
				patch.load_fxt(fxt_filepath, fxt_id, fxt_univ, fxt_addr)
			if c2 == "reset":
				patch.reset()
	if c == "set" :
		ui = getinput(2*"channel=value, ", " ... or all=value", sep="", end="\n")
		ui = ui.split(',')
		for x in ui:
			i = x.split('=')
			if i[0] == "all" :
				universes[currentUniv].set_allchannels(i[1])
			else :
				universes[currentUniv].set_value(*i)
		del ui, x, i
	if c == "univ":
		currentUniv = None
		while not currentUniv in universes.keys():
			if not currentUniv is None : print("Universe", currentUniv, "doesn't exist.")
			currentUniv = getintinput("Which universe do you want to handle ?", end="\n")
	if c == "reset" :
		universes[currentUniv].reset()
	if c == "dmxdata":
		print(universes[currentUniv].get_dmxdata())
	if c == "clients":
		if server.getclients() != {} :
			for client in server.clients.values():
				print("- client ", client.n, " from ", client.ip, ":", client.port, sep="", end="\n")
		else : print("No client connected.")
	if c == "disconnect" :
		ui = getinput("Id the of client you want to disconnect, or id,id,id...", end="\n")
		for n in ui.split(','):
			if n.isdigit() :
				server.removeclient(to_int(n))
		del ui, n
	if c == "stop" :
		server.stoplistening()
	if c == "start" :
		server.startlistening()
	if c == "q" or c == "quit" or c == "shutdown" :
		shutdown()
	print("\n", 6*" "+12*"*", end="\n\n")
