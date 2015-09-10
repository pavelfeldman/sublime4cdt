import json
import os
import sys
import http.client
import sublime
import sublime_plugin

sys.path.append(os.path.join(os.path.dirname(__file__), 'py'))

from ws4py.websocket import WebSocket
from ws4py.client.threadedclient import WebSocketClient

class DevToolsSync(sublime_plugin.EventListener):
    def __init__(self):
        self.socket_ = SocketClient(self, 'ws://127.0.0.1:9222/devtools/frontend_api', protocols=['http-only', 'chat'])
        self.id_ = 1
        self.muted_views_ = set()

    def on_activated(self, view):
        self.active_view_ = view
        view.erase_regions('reveal')

    def is_muted(self, view):
        return view.id() in self.muted_views_

    def on_modified(self, view):
        if self.is_muted(view):
            return
        self.send('Frontend.updateBuffer', {'file': view.file_name(), 'buffer': view.substr(sublime.Region(0, view.size()))});
        view.erase_regions('reveal')

    def on_post_save(self, view):
        if self.is_muted(view):
            return
        self.send('Frontend.updateBuffer', {'file': view.file_name(), 'buffer': view.substr(sublime.Region(0, view.size())), 'saved': True});

    def dispatch_notification(self, event):
        if not 'method' in event:
            return
        print(event['method'])
        if event['method'] == 'Frontend.bufferUpdated':
            file = event['params']['file']
            buffer = event['params']['buffer']
            for window in sublime.windows():
                view = window.find_open_file(file)
                if view:
                    self.muted_views_.add(view.id())
                    view.run_command('replace_content', {'payload': buffer})
                    if 'saved' in event['params']:
                        view.run_command('save')
                    self.muted_views_.remove(view.id())
        if event['method'] == 'Frontend.revealLocation':
            file = event['params']['file']
            for window in sublime.windows():
                view = window.open_file(file)
                if view:
                    point = view.text_point(event['params']['line'], 0)
                    region = view.full_line(point)
                    region.b -= 1
                    view.sel().clear()
                    view.sel().add(sublime.Region(region.b, region.b))
                    view.show(view.sel())
                    view.add_regions('reveal', [region], 'invalid')
                    view.show(region)
                    view.window().focus_view(view)

    def send(self, method, params):
        if not self.socket_:
            self.socket_ = SocketClient(self, 'ws://127.0.0.1:9222/devtools/frontend_api', protocols=['http-only', 'chat']);
        self.id_ += 1
        print(method)
        self.socket_.post_command(json.dumps({ 'method': method, 'params': params, 'id': self.id_ }))

class ReplaceContentCommand(sublime_plugin.TextCommand):
    def run(self, edit, payload=None, **kwargs):
        if self.view.substr(sublime.Region(0, self.view.size())) == payload:
            return
        viewport = self.view.viewport_position()
        self.view.replace(edit, sublime.Region(0, self.view.size()), payload)
        self.view.set_viewport_position(viewport)

class SocketClient(WebSocketClient):
    def __init__(self, sync, url, protocols):
        super(SocketClient, self).__init__(url, protocols) 
        self.sync_ = sync
        self.opened_ = False
        self.pending_commands_ = []
        self.connect()

    def post_command(self, command):
        if self.opened_:
            self.send(command)
        else:
            self.pending_commands_.append(command)

    def opened(self): 
        print('connection opened')
        self.opened_ = True
        for command in self.pending_commands_:
            self.send(command)
        self.pending_commands_ = [];

    def closed(self, code, reason=None):
        print('connection closed')
        self.opened_ = False
        self.sync_.socket_ = None

    def received_message(self, m):
        self.sync_.dispatch_notification(json.loads(str(m)))
