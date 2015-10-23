import glob
import json
import os
import sys
import http.client
import sched
import sublime
import sublime_plugin
import time

from functools import partial

sys.path.append(os.path.join(os.path.dirname(__file__), 'py'))

from ws4py.websocket import WebSocket
from ws4py.client.threadedclient import WebSocketClient
from diff.diff_match_patch import diff_match_patch

pending_reveal_lines_ = {}

class DevToolsSync(sublime_plugin.EventListener):
    def __init__(self):
        self.socket_ = SocketClient(self, 'ws://127.0.0.1:9222/devtools/frontend_api', protocols=['http-only', 'chat'])
        self.id_ = 1
        self.muted_views_ = set()
        self.file_systems_ = []

    def on_activated(self, view):
        self.active_view_ = view
        self.remove_markers_(view)

    def on_load(self, view):
        if view.file_name() in pending_reveal_lines_:
            view.run_command('reveal_line', { 'line': pending_reveal_lines_[view.file_name()] })
            del pending_reveal_lines_[view.file_name()]
            view.pending_line_ = None

    def is_muted(self, view):
        return view.id() in self.muted_views_

    def on_modified(self, view):
        self.remove_markers_(view)
        if self.is_muted(view) or not self.is_file_in_project_(view):
            return
        self.send_('Frontend.updateBuffer', {'file': view.file_name(), 'buffer': view.substr(sublime.Region(0, view.size()))});
        view.erase_regions('reveal')

    def on_post_save(self, view):
        if self.is_muted(view) or not self.is_file_in_project_(view):
            return
        self.send_('Frontend.updateBuffer', {'file': view.file_name(), 'buffer': view.substr(sublime.Region(0, view.size())), 'saved': True});

    def on_post_save_async(self, view):
        self.post_filesystems_()

    def is_file_in_project_(self, view):
        file_name = view.file_name()
        if file_name == None:
            return False
        for path in self.file_systems_:
            if file_name.startswith(path):
                return True
        return False

    def dispatch_notification_(self, event):
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
                view.run_command('reveal_line', { 'line': event['params']['line'] })

    def send_(self, method, params):
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
        self.file_systems_ = []
        for config in configs:
            self.file_systems_.append(config[:-10])
        self.send_('Frontend.addFileSystem', { 'paths': self.file_systems_ })

class ReplaceContentCommand(sublime_plugin.TextCommand):
    def run(self, edit, payload=None, **kwargs):
        old_content = self.view.substr(sublime.Region(0, self.view.size()))
        if old_content == payload:
            return
        viewport = self.view.viewport_position()
        self.view.replace(edit, sublime.Region(0, self.view.size()), payload)
        diff = diff_match_patch().diff_lineMode(old_content, payload, time.time() + 10)
        offset = 0
        begin = 0
        end = 0
        for item in diff:
            if item[0] == 1 and begin == 0:
                begin = offset
            if item[0] != -1:
                offset += len(item[1])
            if item[0] == 1:
                end = offset
        self.view.add_regions('diff', [sublime.Region(begin, end)], 'comment')
        self.view.set_viewport_position(viewport)
        sublime.set_timeout(partial(self.set_viewport_position_, viewport), 0)
        sublime.set_timeout(self.clear_diff_markers_, 150)

    def set_viewport_position_(self, viewport):
        self.view.set_viewport_position(viewport)

    def clear_diff_markers_(self):
        self.view.erase_regions('diff')

class RevealLineCommand(sublime_plugin.TextCommand):
    def run(self, edit, line=None, **kwargs):
        if self.view.is_loading():
            pending_reveal_lines_[self.view.file_name()] = line
            return
        point = self.view.text_point(line, 0)
        region = self.view.line(point)
        self.view.sel().clear()
        self.view.add_regions('reveal', [region], 'invalid')
        self.view.show(sublime.Region(region.a, region.a))
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
        self.sync_.dispatch_notification_(json.loads(str(m)))
