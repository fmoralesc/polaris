#!/usr/bin/python2
#coding: utf8
import sys
import os
import fcntl
import argparse
import signal
import atexit
import time
from datetime import datetime
import subprocess
import gobject
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop

def fill_ro(string):
	return string.replace("^ro", "^r")

class PolarisManager(dbus.service.Object):
	def __init__(self):
		global pid

		bus_name = dbus.service.BusName('org.polaris.service', bus=dbus.SessionBus())
		dbus.service.Object.__init__(self, bus_name, '/org/polaris/service')
		
		from ConfigParser import RawConfigParser as configparser
		import wnck
 
		config = configparser()
		config.readfp(open(os.path.expanduser("~/.polarisrc")))
		self.DZEN2_OPTS = config.get("General", "dzen2_opts")
		self.WORKSPACES_NFG = config.get("Workspaces", "normal_fg")
		self.WORKSPACES_NBG = config.get("Workspaces", "normal_bg")
		self.WORKSPACES_AFG = config.get("Workspaces", "active_fg")
		self.WORKSPACES_ABG = config.get("Workspaces", "active_bg")
		self.TASKS_NFG = config.get("Tasks", "normal_fg")
		self.TASKS_NBG = config.get("Tasks", "normal_bg")
		self.TASKS_AFG = config.get("Tasks", "active_fg")
		self.TASKS_ABG = config.get("Tasks", "active_bg")
		self.TASKS_IFG = config.get("Tasks", "iconiz_fg")
		self.TASKS_IBG = config.get("Tasks", "iconiz_bg")
		self.CLOCK_FG = config.get("Clock", "clock_fg")
		self.CLOCK_FORMAT = config.get("Clock", "strftime")
		
		dzen2_invocation = ["/usr/bin/dzen2", "-p"]
		dzen2_invocation.extend(self.DZEN2_OPTS.split())
		self.dzen2_pipe = subprocess.Popen(dzen2_invocation, 
				stdout=subprocess.PIPE, 
				stderr=subprocess.PIPE, 
				stdin=subprocess.PIPE, close_fds=True) 
		pid = self.dzen2_pipe.pid
		#gobject.timeout_add(100, self.is_dzen2_running)

		self.screen = wnck.screen_get_default()
		self.screen.force_update()
		self.screen.connect("active-workspace-changed", self.get_workspaces)
		self.screen.connect("workspace-created", self.get_workspaces)
		self.screen.connect("workspace-destroyed", self.get_workspaces)
		self.screen.connect("active-window-changed", self.get_windows)
		self.screen.connect("window-opened", self.get_windows)
		self.screen.connect("window-closed", self.get_windows)
		self.screen.connect

		self.last_event = 0
		self.get_workspaces()
		self.get_windows()
		self.get_time()
		self.output_dzen_line()
		gobject.timeout_add(10000, self.get_time)

	def is_dzen2_running(self, *args):
		global pid
		print "PID:", pid
		if not os.path.exists("/proc/"+str(pid)):
			sys.exit(0)
		return True
	
	def get_workspaces(self, *args):
		def nfg(workspace):
			return "^fg(" + self.WORKSPACES_NFG + ")" + workspace + "^fg()"
		def nbg(workspace):
			return "^bg(" + self.WORKSPACES_NBG + ")" + workspace + "^bg()"
		def afg(workspace):
			return workspace.replace("^fg(" + self.WORKSPACES_NFG, "^fg(" + self.WORKSPACES_AFG)
		def abg(workspace):
			return workspace.replace("^bg(" + self.WORKSPACES_NBG, "^bg(" + self.WORKSPACES_ABG)
		def ca_workspace(workspace, workspace_name):
			return "^ca(1, polaris.py -w " + workspace_name + ")" + workspace + "^ca()"

		wm_workspaces = self.screen.get_workspaces()
		workspaces = []
		count = 0
		for workspace in wm_workspaces:
			workspace.connect("name-changed", self.get_workspaces)
			workspaces.append(ca_workspace(nbg(nfg("^p(;2)^ro(4x4)^p(;-2) " + workspace.get_name() + " ")), workspace.get_name()))
			count = count + 1
		active_workspace = self.screen.get_active_workspace().get_number()
		workspaces[active_workspace] = fill_ro(abg(afg(workspaces[active_workspace])))
		self.workspaces = " ".join(workspaces) + "^p()"
		self.get_windows()
		if args:
			self.output_dzen_line()

	# we must forbid too fast window name changes
	# TODO: make it work HONESTLY
	def filter_name_change(self, *args):
		event_time = time.time()
		delta = event_time - self.last_event
		self.last_event = event_time
		if delta >= 1:
			self.get_windows(True)
			
	def get_windows(self, *args):
		def nfg(task):
			return "^fg(" + self.TASKS_NFG + ")" + task + "^fg()"
		def nbg(task):
			return "^bg(" + self.TASKS_NBG + ")" + task + "^bg()"
		def ifg(task):
			return task.replace("^fg(" + self.TASKS_NFG, "^fg(" + self.TASKS_IFG)
		def ibg(task):
			return task.replace("^fg(" + self.TASKS_NBG, "^fg(" + self.TASKS_IBG)
		def afg(task):
			return task.replace("^fg(" + self.TASKS_NFG, "^fg(" + self.TASKS_AFG)
		def abg(task):
			return task.replace("^bg(" + self.TASKS_NBG, "^bg(" + self.TASKS_ABG)
		def ca_task(task, uniq):
			return " ^ca(1, polaris.py -t " + uniq + ")" + task + "^ca() "
		self.windows = ""
		windows = self.screen.get_windows()
		if windows != None:
			workspaces = self.screen.get_workspaces()
			windows_workspaces_dict = {}
			for workspace in workspaces:
				windows_workspaces_dict[workspace.get_name()] = []
			for window in windows:
				if not window.is_skip_tasklist():
					window_workspace = window.get_workspace()
					if window_workspace != None:
						windows_workspaces_dict[window_workspace.get_name()].append(window)
					else:
							if window.is_sticky() or self.screen.get_window_manager_name() == "Openbox":
								for workspace in windows_workspaces_dict:
									windows_workspaces_dict[workspace].append(window)
			
			cw_window_full_names = []
			active_workspace = self.screen.get_active_workspace().get_name()
			count = 0
			for window in windows_workspaces_dict[active_workspace]:
				window.connect("name-changed", self.filter_name_change)
				window_full_name = unicode(window.get_name())
				window_name = window_full_name
				if len(window_full_name) > 30:
					window_name = window_full_name[:29] + u"\u2026"
				cw_window_full_names.append(ca_task(nbg(nfg("^ro(3x3)  " + window_name)), str(window.get_xid())))
				if window.is_minimized():
					cw_window_full_names[count] = ibg(ifg(cw_window_full_names[count]))
				self.active_window = self.screen.get_active_window()
				if self.active_window != None:
					if window_full_name == self.active_window.get_name():
						cw_window_full_names[count] = fill_ro(abg(afg(cw_window_full_names[count])))
				count = count + 1
				self.windows = "  ".join(cw_window_full_names)
		else:
			self.windows = ""
		if args:
			self.output_dzen_line()

	def get_time(self, *args):
		self.time = "^fg(#"+ self.CLOCK_FG + ")" + datetime.now().strftime(self.CLOCK_FORMAT) + "^fg()"
		self.output_dzen_line()
		return True
	
	def output_dzen_line(self, *args):
		dzen2_line = "^p(2)^fn(droid sans:bold:size=8)" + self.time + "^fn()^p(5)" + self.workspaces + "^p(2)^fg(#808080)^r(1x5)^fg()^p(6)" + self.windows
		self.dzen2_pipe.stdin.write(dzen2_line + "\n")

	@dbus.service.method('org.polaris.service')
	def toggle_window(self, window_xid):
		cw = self.screen.get_active_workspace()

		cw_windows = [ window for window in self.screen.get_windows()]
		for cw_window in cw_windows:
			if str(cw_window.get_xid()) == window_xid:
				if cw_window.is_minimized():
					cw_window.unminimize(1)
					return True
				else:
					if cw_window.is_active():
						cw_window.minimize()
						return True
					else:
						cw_window.activate(1)
						return True
		return False

	@dbus.service.method('org.polaris.service')
	def switch_workspace(self, workspace_name):
		workspaces = self.screen.get_workspaces()
		cw = self.screen.get_active_workspace().get_name()
		for workspace in workspaces:
			if workspace.get_name() == workspace_name != cw:
				workspace.activate(1)
				return True
			elif workspace.get_name() == workspace_name == cw:
				self.screen.toggle_showing_desktop(not self.screen.get_showing_desktop())
				return True
		return False


pid = 0

def cleanup():
	if pid:
		os.kill(pid, 15)

if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("-t", nargs="+", dest="toggled_window")
	parser.add_argument("-w", nargs="+", dest="workspace")
	args = parser.parse_args()
	
	if args.toggled_window or args.workspace:
		try:
			polarisservice = dbus.SessionBus().get_object('org.polaris.service', '/org/polaris/service')
		except:
			print "polaris: dbus service not found"
			sys.exit(0)
		if args.toggled_window != None:
			toggle_window = polarisservice.get_dbus_method('toggle_window', 'org.polaris.service')
			returnval = toggle_window(str(args.toggled_window[0]))
			sys.exit(returnval)
		elif args.workspace != None:
			switch_workspace = polarisservice.get_dbus_method('switch_workspace', 'org.polaris.service')
			returnval = switch_workspace(str(args.workspace[0]))
			sys.exit(returnval)

	pid_file = "/tmp/polaris.pid"
	fp = open(pid_file, 'w')
	try:
		fcntl.lockf(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
	except:
		sys.exit(0)

	atexit.register(cleanup)

	DBusGMainLoop(set_as_default=True)
	PolarisManager()
	loop = gobject.MainLoop()
	loop.run()
