import glob
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
        self.remove_markers_(view)

    def on_load(self, view):
        if self.pending_view_ == view:
            view.run_command('reveal_line', { 'line': self.pending_line_ })
            self.pending_view_ = None
            self.pending_line_ = None

    def is_muted(self, view):
        return view.id() in self.muted_views_

    def on_modified(self, view):
        self.remove_markers_(view)
        if self.is_muted(view):
            return
        self.send('Frontend.updateBuffer', {'file': view.file_name(), 'buffer': view.substr(sublime.Region(0, view.size()))});
        view.erase_regions('reveal')

    def on_post_save(self, view):
        if self.is_muted(view):
            return
        self.send('Frontend.updateBuffer', {'file': view.file_name(), 'buffer': view.substr(sublime.Region(0, view.size())), 'saved': True});

    def on_post_save_async(self, view):
        self.post_filesystems_()

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
            print('Reveal location:' + event['params']['file'])
            file = event['params']['file']
            for window in sublime.windows():
                view = window.open_file(file)
                if not view:
                    return
                if view.is_loading():
                    self.pending_view_ = view
                    self.pending_line_ = event['params']['line']
                    return
                view.run_command('reveal_line', { 'line': event['params']['line'] })

    def send(self, method, params):
        if not self.socket_:
            self.socket_ = SocketClient(self, 'ws://127.0.0.1:9222/devtools/frontend_api', protocols=['http-only', 'chat']);
        self.id_ += 1
        print(method)
        self.socket_.post_command(json.dumps({ 'method': method, 'params': params, 'id': self.id_ }))

    def remove_markers_(self, view):
        view.erase_regions('reveal')

    def post_filesystems_(self):
        configs = []
        for window in sublime.windows():
            folders = window.folders()
            for folder in folders:
                configs += glob.glob(folder + '/**/.devtools') + glob.glob(folder + '/.devtools')
        paths = []
        for config in configs:
            paths.append(config[:-10])
        self.send('Frontend.addFileSystem', { 'paths': paths })

class ReplaceContentCommand(sublime_plugin.TextCommand):
    def run(self, edit, payload=None, **kwargs):
        if self.view.substr(sublime.Region(0, self.view.size())) == payload:
            return
        viewport = self.view.viewport_position()
        self.view.replace(edit, sublime.Region(0, self.view.size()), payload)
        self.view.set_viewport_position(viewport)

class RevealLineCommand(sublime_plugin.TextCommand):
    def run(self, edit, line=None, **kwargs):
       point = self.view.text_point(line, 0)
       region = self.view.line(point)
       self.view.sel().clear()
       self.view.show(self.view.sel())
       self.view.add_regions('reveal', [region], 'invalid')
       self.view.show(region)
       self.view.window().focus_view(self.view)
  

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

