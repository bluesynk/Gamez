import cherrypy
import os
import threading
import gamez
from jinja2 import Environment, PackageLoader
from gamez import common, GameTasks, ActionManager
from classes import *
from gamez.Logger import LogEvent, DebugLogEvent
from FileBrowser import WebFileBrowser


class WebRoot:
    appPath = ''

    def __init__(self,app_path):
        WebRoot.appPath = app_path
        self.env = Environment(loader=PackageLoader('html', 'templates'))

    def _globals(self):
        return {'p': Platform.select(), 's': Status.select()}

    @cherrypy.expose
    def index(self, status_message='', version=''):
        template = self.env.get_template('index.html')
        gs = Game.select()
        return template.render(games=gs, **self._globals())

    @cherrypy.expose
    def search(self, term='', platform=''):
        template = self.env.get_template('search.html')
        games = {}
        if term:
            for provider in common.PM.P:
                LogEvent("Searching on %s" % provider.name)
                games[provider.name] = provider.searchForGame(term, Platform.get(Platform.id == platform))

        return template.render(games=games, **self._globals())

    @cherrypy.expose
    def settings(self):
        template = self.env.get_template('settings.html')
        return template.render(plugins=common.PM.getAll(True), **self._globals())

    @cherrypy.expose
    def createInstance(self, plugin, instance):
        c = None
        for cur_plugin in common.PM.getAll(True):
            if cur_plugin.type == plugin and not cur_plugin.single:
                c = cur_plugin.__class__(instance=instance)
                break
        common.PM.cache()
        url = '/settings/'
        if c:
            url = '/settings/#%s' % c.name.replace(' ', '_')
        raise cherrypy.HTTPRedirect(url)

    @cherrypy.expose
    def removeInstance(self, plugin, instance):
        for cur_plugin in common.PM.getAll(True):
            if cur_plugin.type == plugin and cur_plugin.instance == instance:
                c = cur_plugin.deleteInstance()
                break
        common.PM.cache()
        raise cherrypy.HTTPRedirect('/settings/')

    @cherrypy.expose
    def saveSettings(self, **kwargs):
        actions = {}
        redirect_to = '/settings/'
        if 'saveOn' in kwargs:
            redirect_to += "#%s" % kwargs['saveOn']
            del kwargs['saveOn']

        def convertV(cur_v):
            try:
                return int(cur_v)
            except TypeError: # its a list for bools / checkboxes "on" and "off"... "on" is only send when checked "off" is always send
                return True
            except ValueError:
                if cur_v in ('None', 'off'):
                    cur_v = False
                return cur_v

        # this is slow !!
        # because i create each plugin for each config value that is for that plugin
        # because i need the config_meta from the class to create the action list
        # but i can use the plugins own c obj for saving the value
        for k, v in kwargs.items():
            DebugLogEvent("config K:%s V:%s" % (k, v))
            parts = k.split('-')
            # parts[0] plugin class name
            # parts[1] plugin instance name
            # parts[2] config name
            # v value for config -> parts[2]
            class_name = parts[0]
            instance_name = parts[1]
            config_name = parts[2]
            plugin = common.PM.getInstanceByName(class_name, instance_name)
            if plugin:
                DebugLogEvent("We have a plugin: %s (%s)" % (class_name, instance_name))
                old_value = getattr(plugin.c, config_name)
                new_value = convertV(v)
                if old_value == new_value:
                    continue
                setattr(plugin.c, config_name, convertV(v)) # saving value
                if plugin.config_meta[config_name]: # this returns none
                    if 'on_change_actions' in plugin.config_meta[config_name] and old_value != new_value:
                        actions[plugin] = plugin.config_meta[config_name]['on_change_actions'] # this is a list of actions
                    if 'actions' in plugin.config_meta[config_name]:
                        actions[plugin] = plugin.config_meta[config_name]['actions'] # this is a list of actions
                    if 'on_enable' in plugin.config_meta[config_name] and new_value:
                        actions[plugin] = plugin.config_meta[config_name]['on_enable'] # this is a list of actions

                continue
            else: # no plugin with that class_name or instance found
                DebugLogEvent("We don't have a plugin: %s (%s)" % (class_name, instance_name))
                continue

        #actions = list(set(actions))
        common.PM.cache()
        final_actions = {}
        for cur_class_name, cur_actions in actions.items():
            for cur_action in cur_actions:
                if not cur_action in final_actions:
                    final_actions[cur_action] = []
                final_actions[cur_action].append(cur_class_name)
        for action, plugins_that_called_it  in final_actions.items():
            ActionManager.executeAction(action, plugins_that_called_it)
        
        raise cherrypy.HTTPRedirect(redirect_to)

    @cherrypy.expose
    def log(self):
        template = self.env.get_template('index.html')
        gs = Game.select()
        return template.render(games=gs, **self._globals())

    @cherrypy.expose
    def comingsoon(self):
        template = self.env.get_template('index.html')
        gs = Game.select()
        return template.render(games=gs, **self._globals())

    @cherrypy.expose
    def addGame(self, gid, p='TheGameDB'):
        gid = int(gid)
        for provider in common.PM.P:
            if provider.type == p:
                game = provider.getGame(gid)
                if game:
                    game.save()
                    GameTasks.searchGame(game)

        raise cherrypy.HTTPRedirect('/')

    @cherrypy.expose
    def removegame(self, gid):
        q = Game.delete().where(Game.id == gid)
        q.execute()
        raise cherrypy.HTTPRedirect('/')

    @cherrypy.expose
    def updateStatus(self, gid, s):
        g = Game.get(Game.id == gid)
        g.status = Status.get(Status.id == s)
        if g.status == common.WANTED:
            GameTasks.searchGame(g)
        raise cherrypy.HTTPRedirect('/')

    @cherrypy.expose
    def updategamelist(self):
        #addAllWii()
        #AddWiiGamesIfMissing()
        #AddXbox360GamesIfMissing()
        #AddComingSoonGames()
        status = "Game list has been updated successfully"
        raise cherrypy.HTTPRedirect("/?status_message=" + status)

    @cherrypy.expose
    def shutdown(self):
        cherrypy.engine.exit()
        status = "Gamez will be shutting down!!! Bye"
        raise cherrypy.HTTPRedirect("/?status_message=" + status)

    @cherrypy.expose
    def reboot(self):
        ActionManager.executeAction('executeAction', 'Webgui')
        raise cherrypy.HTTPRedirect("/")

    @cherrypy.expose
    def forcesearch(self, gid):
        GameTasks.searchGame(Game.get(Game.id == gid))
        raise cherrypy.HTTPRedirect('/')

    @cherrypy.expose
    def refreshinfo(self, gid, p='TheGameDB'):
        DebugLogEvent("init update")
        game = Game.get(Game.id == gid)
        for provider in common.PM.P:
            if provider.type == p:
                new = provider.getGame(game.tgdb_id)
                game.name = new.name
                game.boxart_url = new.boxart_url
                game.genre = new.genre
                game.overview = new.overview
                game.save()
                game.cacheImg()

        raise cherrypy.HTTPRedirect('/')

    browser = WebFileBrowser()
