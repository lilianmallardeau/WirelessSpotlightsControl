"""
Client
v3

"""


# ------------------------ LIBRAIRIES IMPORT ------------------------ #
from common import *
#import kivy
from kivy.app import App
from kivy.lang import Builder
from kivy.uix.widget import Widget
from kivy.uix.gridlayout import GridLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.label import Label
from kivy.uix.slider import Slider
from kivy.uix.button import Button
from kivy.uix.screenmanager import *
from kivy.clock import Clock

# ------------------------ CLIENT PARAMETERS ------------------------ #
console_mode_alive = True
DynamicUI = True
currentUniv = False
LoginScreenPadding = 200
LoginScreenSpacing = 50
DmxSlidersLatency = 4 # in seconds

# ---------------------- FUNCTIONS AND CLASSES ---------------------- #
class DmxManager():
	"""docstring for DmxFunctions"""
	def __init__(self):
		self.universes = {}
		self.last_updated_univs = {}
	def get_dmxdata(self, univ):
		if not univ in self.universes.keys(): return None
		return self.universes[univ]

	# Functions called by Client class
	def update_univ(self, univ, dmxdata):
		global currentUniv, App
		self.universes[univ] = dmxdata
		self.last_updated_univs[univ] = time.time()
		App.update_univ_values(univ=univ, dmxdata=self.universes[univ])
		if currentUniv is False: currentUniv = univ
	
	# Functions called by root app class (kivy)
	def set_dmxvalue(self, univ, channel, value):
		global App
		App.Client.send_command("setdmxchannel", univ, channel, value)
	def set_allchannels(self, univ, value):
		global App
		App.Client.send_command("setallchannels", univ, value)
	def reset_univ(self, n):
		global App
		App.Client.send_command("resetuniv", n)

class Patch():
	"""docstring for Patch"""
	def __init__(self):
		self.previous_patch = {}
		self.patch = {}
		self.last_updated = 0
	# Functions called by Client class
	def update(self, patch):
		global App
		if type(patch) is not dict: return False
		self.previous_patch = copy(self.patch)
		self.patch = patch
		self.last_updated = time.time()
		return App.update_patch(self.previous_patch, self.patch)

	# Functions called by Kivy events manager
	def add_fxt(self, fxt_id, fxt_univ, fxt_addr, fxt):
		global App
		App.Client.send_command("addfxt", fxt_id, fxt_univ, fxt_addr, json.dumps(fxt))
	def remove_fxt(self, fxt_id):
		global App
		App.Client.send_command("removefxt", fxt_id)

class Client(Thread):
	"""docstring for Client"""
	def __init__(self, host, port, autoconnect=False):
		super(Client, self).__init__()
		self.host = host
		self.port = port
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.listeningThread = Thread(target=self.listening, args=())
		self.sendingThread = Thread(target=self.sending, args=())
		self.listeningActive = True
		self.sendingActive = True
		self.commands_queue = Queue()
		self.is_authentified = False
		if autoconnect == True: self.start()
	def run(self):
		self.sock.connect((self.host, self.port))
		self.listeningThread.start()
		self.sendingThread.start()
	def listening(self):
		while self.listeningActive:
			current_command = str()
			while not current_command.endswith(EOC):
				current_command += self.sock.recv(1).decode()
			self.commandManager(current_command[:-len(EOC)])
	def sending(self):
		while self.sendingActive:
			command = self.commands_queue.get()
			if type(command) is not str: break
			if command == "pass": return
			sent = 0
			while sent < len(command):
				sent += self.sock.send(command[-(len(command)-sent):].encode())
	def send_command(self, *args):
		args = [str(arg) for arg in args]
		command = ParamsSep.join(args) + EOC
		self.commands_queue.put(command)
	def commandManager(self, command):
		global App
		command = command.split(ParamsSep)
		action = str(command[0]).lower()
		if action == "authentified":
			self.authentified()
		if action == "unauthentified":
			self.unauthentified()
		if action == "dmxdata":
			univ = command[1]
			if not is_int(univ): return False
			dmxdata = convert_container_elements(json.loads(command[2]))
			App.DmxManager.update_univ(to_int(univ), dmxdata)
		if action == "patch":
			patch = convert_container_elements(json.loads(command[1]))
			App.Patch.update(patch)
	def authentify(self, passwd):
		self.send_command("authentify", passwd)
	def authentified(self):
		global App
		self.is_authentified = True
		App.authentified()
	def unauthentified(self):
		global App
		self.is_authentified = False
		App.unauthentified()
	def close(self, send=True):
		if send: self.send_command("disconnect")
		self.listeningActive = False
		self.sock.close()


def shutdown():
	global App
	App.Client.close()
	exit(exit_msg)

def console_mode():
	global console_mode_alive, currentUniv
	while console_mode_alive:
		print("What to do ?")
		actions = []
		f = "- "
		actions.append("Set channel(s) value(s) [set]")
		actions.append("Reset universe [reset]")
		actions.append("Change universe to handle [univ]")
		actions.append("Print DMX Data of current universe [dmxdata]")
		actions.append("Print patch [patch]")
		actions.append("Quit [q] [quit]")
		actions = [f+action for action in actions]
		with printLock:
			print(*actions, sep="\n", end="\n")
			print("Actions apply on universe", currentUniv, sep=" ", end="\n")
		c = getinput().lower()
		if c == "set" :
			ui = getinput(2*"channel=value, ", " ... or all=value", sep="", end="\n")
			ui = ui.split(',')
			for x in ui:
				i = x.split('=')
				if i[0] == "all" :
					App.DmxManager.set_allchannels(currentUniv, i[1])
				else :
					App.DmxManager.set_dmxvalue(currentUniv, *i)
		if c == "reset" :
			App.DmxManager.reset_univ(currentUniv)
		if c == "univ" :
			currentUniv = None
			while not currentUniv in App.DmxManager.universes.keys():
				if not currentUniv is None : print("Universe", currentUniv, "doesn't exist.")
				currentUniv = getintinput("Which universe do you want to handle ?", end="\n")
		if c == "dmxdata":
			print(App.DmxManager.get_dmxdata(currentUniv))
		if c == "patch" :
			print(json.dumps(App.Patch.patch, indent=4))
		if c == "q" or c == "quit":
			shutdown()
			return
		print()

# --------------------------- KIVY CLASSES -------------------------- #
class LoginScreen(Screen):
	pass
class PasswordScreen(Screen):
	pass
class ConnectionErrorScreen(Screen):
	text = "Error during connection"
	buttontext = "Okay... try again!"
	def set_text(self, text):
		self.text = text
	def set_buttontext(self, text):
		self.buttontext = text
class SynchronisingScreen(Screen):
	pass	
class ApplicationScreen(Screen):
	pass
class CreateFixtureScreen(Screen):
	channel_n = 1
	channels = {}
	def add_channel(self):
		if not is_dmxvalue(self.channel_default_value.text): return False
		self.channels[self.channel_n] = {"name": self.channel_name.text, "default": self.channel_default_value.text}
		self.channel_name.text = str()
		self.channel_default_value.text = str()
		self.channel_n += 1
		self.set_addchnlbtn_text()
	def createfxt(self):
		global App
		if self.fxt_name.text == str(): return False
		if not self.fxt_id.text.isnumeric(): return False
		if not self.univ.text.isnumeric(): return False
		if not is_dmxchannel(self.addr.text): return False
		if self.channels == {}: return False
		name = self.fxt_name.text
		brand = self.brand.text
		type = self.type.text
		fxt = {"name": name, "brand": brand, "type": type, "channels": self.channels}
		id = self.fxt_id.text
		univ = self.univ.text
		addr = self.addr.text
		App.Patch.add_fxt(id, univ, addr, fxt)
		self.reset()
		App.mainScreen()
	def set_addchnlbtn_text(self):
		self.add_chnl_button.text = "Add channel " + str(self.channel_n)
	def reset(self):
		textinputs = [self.fxt_name, self.brand, self.type, self.fxt_id, self.univ, self.addr, self.channel_name, self.channel_default_value]
		for textinput in textinputs:
			textinput.text = str()
		self.channels = {}
		self.channel_n = 1
		self.set_addchnlbtn_text()
class DmxSlider(Slider):
	"""docstring for DmxSlider"""
	def __init__(self, *args, **kwargs):
		if not "min" in kwargs.keys(): kwargs["min"] = minChannelValue
		if not "max" in kwargs.keys(): kwargs["max"] = maxChannelValue
		if not "step" in kwargs.keys(): kwargs["step"] = 1
		super(DmxSlider, self).__init__(*args, **kwargs)
	def on_touch_down(self, touch):
		if Slider.on_touch_down(self, touch):
			self.busy = True
			global App
			App.on_slider_value(self, self.value)
			return True
	def on_touch_move(self, touch):
		if Slider.on_touch_move(self, touch):
			global App
			App.on_slider_value(self, self.value)
			return True
	def on_touch_up(self, touch):
		if Slider.on_touch_up(self, touch):
			Clock.schedule_once(self.ready, DmxSlidersLatency)
			return True
	def ready(self, dt):
		self.busy = False
class Fixture(BoxLayout):
	"""docstring for Fixture"""
	def __init__(self, id, patch, fixture, autobuild=True):
		super(Fixture, self).__init__()
		self.fxtid = id
		self.univ = patch["univ"]
		self.dmxaddr = patch["addr"]
		self.fxt = fixture
		self.name = fixture["name"]
		self.brand = fixture["brand"]
		self.type = fixture["type"]
		self.channels = fixture["channels"]
		self.sliders = {}
		self.boxes = []
		self.orientation = "vertical"
		if autobuild: self.build()
	def build(self):
		global App
		self.fxtlabel = Label(text=(self.name + "\n" + self.brand), size_hint=(1,  1/(len(self.channels)+1)))
		if DynamicUI: self.boxes.append(self.fxtlabel)
		else: self.add_widget(self.fxtlabel)
		for channel, params in self.channels.items():
			dmxchannel = self.dmxaddr + channel - 1
			box = BoxLayout(orientation="horizontal")
			channel_label = Label(text=str(params["name"])+"\n"+str(dmxchannel), size_hint=(.25, 1))
			box.add_widget(channel_label)
			slider = DmxSlider(value=params["default"])
			slider.busy = False
			slider.rootfxt = self
			slider.dmxchannel = dmxchannel
			slider.fxtchannel = channel
			slider.valuelabel = Label(text=str(int(slider.value)), size_hint=(.25, 1))
			# DO NOT UNCOMMENT THIS LINE
			# slider.bind(value=App.on_slider_value)
			self.sliders[channel] = slider
			if not self.univ in App.sliders.keys():
				App.sliders[self.univ] = {}
			App.sliders[self.univ][dmxchannel] = slider
			box.add_widget(slider)
			box.add_widget(slider.valuelabel)
			if DynamicUI: self.boxes.append(box)
			else: self.add_widget(box)

class ClientApplication(App):
	def __init__(self):
		App.__init__(self)
		self.DmxManager = DmxManager()
		self.DmxManager.App = self
		self.Patch = Patch()
		self.Patch.App = self
		self.screenmanager = ScreenManager(transition=SlideTransition())
		self.screenmanager.add_widget(LoginScreen())
		self.screenmanager.add_widget(PasswordScreen())
		self.screenmanager.add_widget(ConnectionErrorScreen())
		self.screenmanager.add_widget(SynchronisingScreen())
		self.screenmanager.add_widget(CreateFixtureScreen())
		self.appScreen = ApplicationScreen(name="mainscreen")
		self.appScreenLayout = BoxLayout(orientation="vertical", padding=20)
		self.appScreen.add_widget(self.appScreenLayout)
		self.screenmanager.add_widget(self.appScreen)
		self.fixtures = {}
		self.sliders = {}
	def build(self):
		return self.screenmanager
	def connect(self, server, port):
		if not is_int(port): return False
		self.Client = Client(server, to_int(port))
		self.Client.start()
		self.screenmanager.current = "password"
	def authentify(self, password):
		self.Client.authentify(password)
	def authentified(self):
		Thread(target=console_mode, args=()).start()
		self.mainScreen()
	def unauthentified(self):
		global console_mode_alive, currentUniv
		console_mode_alive = False
		currentUniv = False
		self.appScreenLayout.clear_widgets()
		self.screenmanager.current = "connection_error"
	def loginScreen(self):
		self.screenmanager.current = "loginscreen"
	def mainScreen(self):
		self.screenmanager.current = "mainscreen"
	def createFxtScreen(self):
		self.screenmanager.current = "createfxt"
	def update_univ_values(self, univ=None, dmxdata=None):
		if univ is None or dmxdata is None: return False
		if not univ in self.sliders.keys(): return False
		for index in range(len(dmxdata)):
			channel = index + 1
			dmxvalue = dmxdata[index]
			if channel in self.sliders[univ].keys():
				# Check if user is using slider before assign new value to it
				if not self.sliders[univ][channel].busy:
					self.sliders[univ][channel].value = dmxvalue
					self.sliders[univ][channel].valuelabel.text = str(dmxvalue)
	def update_patch(self, previous_patch, patch):
		self.appScreenLayout.clear_widgets()
		self.fixtures = {}
		self.sliders = {}
		for id, fxt in patch.items():
			self.fixtures[id] = Fixture(id, fxt["patch"], fxt["fxt"])
			if not DynamicUI:
				self.appScreenLayout.add_widget(self.fixtures[id])
		if DynamicUI:
			for fxt in self.fixtures.values():
				for box in fxt.boxes:
					self.appScreenLayout.add_widget(box)
		self.appScreenLayout.add_widget(Button(text="Add fixture", on_press=lambda x: self.createFxtScreen()))
	def on_slider_value(self, instance, value):
		instance.valuelabel.text = str(int(value))
		self.DmxManager.set_dmxvalue(instance.rootfxt.univ, instance.dmxchannel, value)


# ------------------------- STARTING CLIENT ------------------------- #
printLock = RLock()

Builder.load_file("ClientApplication.kv")
App = ClientApplication()
App.run()
