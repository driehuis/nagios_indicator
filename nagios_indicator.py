# -*- coding: utf-8 -*-

import six
import re
#import pygtk
#pygtk.require('2.0')

import urllib.request
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk as gtk
gi.require_version('AppIndicator3', '0.1')
from gi.repository import AppIndicator3
gi.require_version('Notify', '0.7')
from gi.repository import Notify
from gi.repository import GObject
from gi.repository import GLib

#import gtk
#import gobject
#import appindicator
#import pynotify
import notify2
import configparser as ConfigParser
import sys
import os
from urllib.error import URLError, HTTPError
from nagios_checker import get_new_nagios_status


CHECK_INTERVAL = 60 * 5 * 1000 # mls

NAGIOS_ICON = 'nagios'
WARNING_ICON = 'warning'
CRITICAL_ICON = 'critical'
SETTINGS_ICON = 'settings'
NETWORK_ICON = 'unknown'

SETTINGS_ERR_MSG = {
    'header': 'CONFIG ERROR',
    'body': 'please, check config file',
}
NETWORK_ERR_MSG = {
    'header': 'NETWORK ERROR',
    'body': '',
}
ICONS_PATH = os.path.join(os.path.realpath(os.path.dirname(
    os.path.abspath(__file__))), 'icons')


class NagiosApplet(object):
    """ Nagios checker applet
    """

    def __init__(self):
        notify2.init("Init")
        self.ind = AppIndicator3.Indicator.new("nagios-checker",
            ICONS_PATH + '/' + NAGIOS_ICON + '.png',
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS)
        self.check_interval = CHECK_INTERVAL

    def run(self):
        self.build_menu()
        self.prepare()
        gtk.main()

    def prepare(self):
        self.set_icon()
        self.renotify = False
        self.show_disabled = False
        self.auth = {}
        self.nagios_status = {}
        self.get_config()
        self.check_status()
        self.timeout_id = GLib.timeout_add(self.check_interval,
            self.check_status)

    def build_menu(self):
        """Create menu
        """
        menu = gtk.Menu()
        item = gtk.MenuItem(label="Check nagios status now")
        menu.append(item)
        item.connect("activate", self.check_now)
        item.show()
        item = gtk.MenuItem(label="Reload config")
        menu.append(item)
        item.connect("activate", self.reload_config)
        item.show()
        item = gtk.MenuItem(label="Quit")
        menu.append(item)
        item.connect("activate", self.quit)
        item.show()
        self.ind.set_menu(menu)

    def check_status(self):
        if self.check_config():
            try:
                new_nagios_status = get_new_nagios_status(**self.auth)
            except (HTTPError, URLError, RuntimeError): # issue8797
                self.set_icon(NETWORK_ICON)
                self.notify(**NETWORK_ERR_MSG)
                self.auth = {} # try read config again
            else:
                self.check_err_notifies(new_nagios_status)
                self.check_ok_notifies()
                self.nagios_status = new_nagios_status
                self.update_icon()
        return True

    def check_err_notifies(self, new_nagios_status):
        for host in new_nagios_status:
            for service, state in new_nagios_status[host].items():
                status = re.sub(r"[\\\\']+", '', str(state['status']))
                state['status'] = status
                notify = re.sub(r"[\\\\']+", '', str(state['notify']))
                state['notify'] = notify
                try:
                    old_state = self.nagios_status[host].pop(service)
                    old_status = old_state['status']
                    old_notify = old_state['notify']
                    if status != old_status or self.renotify \
                        or (notify and not old_notify):
                            self.notify(header=host,
                                body='{0} {1}'.format(service, status))
                except KeyError:
                    if notify or self.show_disabled:
                        self.notify(header=host,
                            body='{0} {1}'.format(service, status))

    def check_ok_notifies(self):
        for host in self.nagios_status:
            for service in self.nagios_status[host]:
                self.notify(header=host,
                    body='{0} {1}'.format(service, 'OK'))

    def update_icon(self):
        #update icon after check_status
        icon = None
        st = set()
        for services in self.nagios_status.values():
            for service in services.values():
                if service['notify'] or self.show_disabled:
                    st.add(service['status'])
        if u'CRITICAL' in st:
            icon = CRITICAL_ICON
        elif u'WARNING' in st:
            icon = WARNING_ICON
        self.set_icon(icon)

    def quit(self, menu_item):
        sys.exit(0)

    def check_now(self, menu_item):
        GLib.source_remove(self.timeout_id)
        self.check_status()
        self.timeout_id = GLib.timeout_add(CHECK_INTERVAL,
            self.check_status)

    def get_config(self):
        self.auth = {}
        home_dir = os.path.expanduser("~")
        conf_file = os.path.join(home_dir, '.nagios_checker')
        if os.path.isfile(conf_file):
            conf = ConfigParser.ConfigParser()
            conf.read(conf_file)
            params = conf.defaults()
            if conf.has_option('DEFAULT', 'renotify'):
                self.renotify = conf.getboolean('DEFAULT', 'renotify')
            if conf.has_option('DEFAULT', 'show_disabled'):
                self.show_disabled = conf.getboolean('DEFAULT',
                    'show_disabled')
            if conf.has_option('DEFAULT', 'interval'):
                check_interval = conf.get('DEFAULT',
                    'interval')
            try:
                self.check_interval = int(check_interval) * 1000
            except:
                pass
            cred_fields = ['url', 'user', 'passwd']
            if all(f in params for f in cred_fields):
                self.auth.update({
                    'url': params['url'],
                    'user': params['user'],
                    'passwd': params['passwd'],
                    })

    def check_config(self):
        if not self.auth:
            self.get_config()
        if not self.auth:
            self.notify(**SETTINGS_ERR_MSG)
            self.set_icon(SETTINGS_ICON)
            return False
        else:
            return True

    def reload_config(self, menu_item):
        """ clear all: icon, status etc.
        start from begin,,, restart check now !
        """
        GLib.source_remove(self.timeout_id)
        self.prepare()

    def set_icon(self, icon=None):
        if icon:
            print("set icon to %s" % icon)
            self.ind.set_status(AppIndicator3.IndicatorStatus.ATTENTION)
            self.ind.set_attention_icon(ICONS_PATH + '/' + icon + '.png')
            self.ind.set_icon(ICONS_PATH + '/' + icon + '.png')
        else:
            print("set icon to None")
            self.ind.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            self.ind.set_icon(ICONS_PATH + '/' + NAGIOS_ICON + '.png')

    def notify(self, header, body=None, type='info'):
        try:
            msg = notify2.Notification(header, body)
            msg.set_timeout(5)
            msg.show()
        except:
            print("Sending desktop notification failed: %s %s" % (header, body))

if __name__ == "__main__":
    applet = NagiosApplet()
    applet.run()
