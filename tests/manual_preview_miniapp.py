"""Local, read-only Mini App preview. No credentials or live API requests."""
from http.server import ThreadingHTTPServer
import importlib
from manual_preview_warm import PreviewHandler
from app import miniapp_ui

DEMO = r"""
  const demoProfile = {
    user: {fullName: 'Александр', username: 'alexander', id: 123},
    viewer: {isSelf: true, canViewAdminPanel: true},
    premium: {active: true, lifetime: true, plan: {title: 'Premium'}},
    mine: {rank: 'Исследователь', coins: 1250, totalDepth: 480, level: 4, luck: 35},
    social: {friends: [], relationships: []}
  };
  api = async (path, options = {}) => {
    if (options.method && options.method !== 'GET') throw new Error('В демо изменения не сохраняются.');
    if (path === '/miniapp/profile/admin') return {
      summary: {chats: 3, admins: 22, moderators: 1, minePlayers: 39, blacklistWords: 1},
      sections: [
        ['roles','Роли'], ['access','Доступ'], ['moderator-roles','Модераторы'],
        ['mine','Настройки шахты'], ['moderation','Настройки тревог'],
        ['rules','Правила'], ['blacklist','Чёрный список'], ['triggers','Триггеры'],
        ['macros','Макросы'], ['inline-stats','Статистика команд']
      ].map(([key,title]) => ({key,title,enabled:true})), build: {shortRevision:'demo'}
    };
    if (path.startsWith('/miniapp/profile/macros')) return {
      chats: [{id:-1001,title:'Ровнее Ровного'},{id:-1002,title:'Фильмы на блекаут'}],
      selectedChatId: -1001,
      macros: [{chatId:-1001,phrase:'встреча',action:'позвать - на встречу\n@demo_user',scope:'chat',enabled:true}]
    };
    if (path.startsWith('/miniapp/profile/access')) return {
      chats: [{id:-1001,title:'Ровнее Ровного'}], selectedChatId:-1001,
      admins:[{user_id:123,full_name:'Александр'}], selectedUserId:0,features:[]
    };
    if (path === '/miniapp/profile') return demoProfile;
    if (path === '/miniapp/reminders') return {reminders: [], weather: {enabled:false}};
    if (path === '/miniapp/mine') return {registered:false, userId:123, name:'Александр', coins:1250};
    if (path === '/miniapp/shop') return {inventory:[], crafting:[], merchant:{total:0,items:[]}};
    if (path.startsWith('/miniapp/rules')) return {
      chats: [], selectedChatId: -1001, selectedChat: {title:'Ровнее Ровного'},
      rulesText: 'Уважайте участников.\nНе публикуйте рекламу и спам.\nОбсуждайте спорные вопросы спокойно.'
    };
    throw new Error('Этот экран не подключён к демо-данным. Реальный API отключён.');
  };
  renderProfile(demoProfile);
"""


class MiniPreviewHandler(PreviewHandler):
    def do_GET(self):
        if self.path.split('?')[0] in {'/', '/mobile'}:
            page = importlib.reload(miniapp_ui).MINI_APP_HTML.replace('  load();', DEMO, 1)
            body = page.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', 4175), MiniPreviewHandler).serve_forever()
