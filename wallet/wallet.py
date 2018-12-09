"""
Proof of concept Python/HTML Wallet for Bismuth, Tornado based

Use --help command line switch to get usage.
"""

import os.path
import re
import json
import logging
import random
import string
import time
import datetime
import tornado.escape
import tornado.httpserver
import tornado.ioloop
import tornado.log
import tornado.locks
import tornado.options
import tornado.web
import unicodedata

from tornado.options import define, options
# from bismuthclient import bismuthapi
from bismuthclient import bismuthclient
from bismuthclient.bismuthutil import BismuthUtil

__version__ = '0.0.61'

define("port", default=8888, help="run on the given port", type=int)
define("debug", default=False, help="debug mode", type=bool)
define("verbose", default=False, help="verbose mode", type=bool)
define("theme", default='themes/material', help="theme directory", type=str)
define("server", default='', help="Force a specific wallet server (ip:port)", type=str)



class Application(tornado.web.Application):
    def __init__(self):
        # wallet_servers = bismuthapi.get_wallet_servers_legacy()
        servers = None
        if options.server:
            servers = [options.server]
        bismuth_client = bismuthclient.BismuthClient(verbose=options.verbose, servers_list=servers)
        bismuth_client.get_server()
        handlers = [
            (r"/", HomeHandler),
            (r"/transactions/(.*)", TransactionsHandler),
            (r"/json/(.*)", JsonHandler),
            (r"/address/(.*)", AddressHandler),
            (r"/messages/(.*)", AddressHandler),
            (r"/wallet/(.*)", WalletHandler),
            (r"/about/(.*)", AboutHandler),
            (r"/tokens/(.*)", TokensHandler),
            (r"/search/(.*)", SearchHandler),
            (r"/cristals/(.*)", CristalsHandler)
        ]
        settings = dict(
            app_title=u"Tornado Bismuth Wallet",
            template_path=os.path.join(os.path.dirname(__file__), options.theme),
            static_path=os.path.join(os.path.dirname(__file__), "{}/static".format(options.theme)),
            ui_modules={"Transaction": TxModule},
            xsrf_cookies=True,
            cookie_secret="__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__",
            login_url="/auth/login",
            compress_response=True,
            debug=options.debug,  # Also activates auto reload
            serve_traceback=options.debug,
            # wallet_servers = wallet_servers
            bismuth_client = bismuth_client,
            bismuth_vars = {'wallet_version': __version__},
            bismuth_cristals = {}
        )
        super(Application, self).__init__(handlers, **settings)


class BaseHandler(tornado.web.RequestHandler):
    def initialize(self):
        """Common init for every request"""
        # TODO: advantage in using Tornado Babel maybe? https://media.readthedocs.org/pdf/tornado-babel/0.1/tornado-babel.pdf
        _ = self.locale.translate
        self.app_log = logging.getLogger("tornado.application")
        self.bismuth = self.settings['bismuth_client']
        # Load persisted wallet if needed
        wallet = self.get_cookie('wallet')
        if wallet and wallet != self.bismuth.wallet_file:
            self.bismuth.load_wallet(wallet)
        # print("cookies", self.cookies)
        self.bismuth_vars = self.settings['bismuth_vars']
        # self.bismuth_vars['wallet'] =
        # reflect server info
        self.settings["page_title"] = self.settings["app_title"]
        self.bismuth_vars['server'] = self.bismuth.info()
        self.bismuth_vars['server_status'] = self.bismuth.status()
        self.bismuth_vars['balance'] = self.bismuth.balance()
        self.bismuth_vars['address'] = self.bismuth_vars['server']['address']
        self.bismuth_vars['params'] = {}
        self.cristals = self.settings['bismuth_cristals']
        # print(self.bismuth_vars)

    def active_if(self, path: string):
        """return the 'active' string if the request uri is the one in path. Used for menu css"""
        if self.request.uri == path:
            return "active"
        return ''

    def active_if_start(self, path: string):
        """return the 'active' string if the request uri begins with the one in path. Used for menu css"""
        if self.request.uri.startswith(path):
            return "active"
        return ''

    def extract_params(self):
        # TODO: rewrite with get_arguments and remove this redundant function
        if '?' not in self.request.uri:
            self.bismuth_vars['params'] = {}
            return {}
        _, param = self.request.uri.split("?")
        res = {key: value for key, value in [item.split('=') for item in param.split("&")]}
        # TODO: see https://www.tornadoweb.org/en/stable/web.html#tornado.web.RequestHandler.decode_argument
        self.bismuth_vars['params'] = res
        return res


class HomeHandler(BaseHandler):
    async def get(self):
        """
        :return:
        """
        # self.render("home.html", balance="101", wallet_servers=','.join(self.settings['wallet_servers']))
        self.bismuth_vars['transactions'] = self.bismuth.latest_transactions(5, for_display=True)
        self.render("home.html", bismuth=self.bismuth_vars)
        # self.app_log.info("> home")


class TransactionsHandler(BaseHandler):

    """
    def randhex(self, size):
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=size))
    """

    async def send(self, params=None):
        query_params = self.extract_params()
        # print(params)
        _ = self.locale.translate
        self.settings["page_title"] = _("Send BIS")
        if query_params.get('recipient', False):
            # We have an address param, it's a confirmation
            self.settings["page_title"] = _("Send BIS: Confirmation")
            type='warning'  # Do not translate
            title=_("Please confirm this transaction")
            message=_("Check this is what you intended to do and hit the \"confirm\" button")
            # TODO: address ok?
            # todo: amount ok
            # todo: enough balance?
            self.render("transactions_send_confirm.html", bismuth=self.bismuth_vars, type=type, title=title,
                        message=message)
        else:
            self.render("transactions_send.html", bismuth=self.bismuth_vars)

    async def confirm(self, params=None):
        amount = self.get_argument("amount")
        recipient = self.get_argument("recipient")
        data = self.get_argument("data", '')
        operation = self.get_argument("operation", '')
        txid = self.bismuth.send(recipient, amount, operation, data)


    async def receive(self, params=None):
        query_params = self.extract_params()
        address = self.bismuth_vars['server']['address']
        _ = self.locale.translate
        self.settings["page_title"] = _("Receive BIS")
        bisurl = ''
        if query_params.get('address', False):
            address = query_params['address']
            bisurl = BismuthUtil.create_bis_url(address, query_params['amount'], '', query_params['data'])
        self.render("transactions_receive.html", bismuth=self.bismuth_vars, address=address, bisurl=bisurl)

    async def get(self, command=''):
        """
        :return:
        """
        command, *params = command.split('/')
        if command:
            await getattr(self, command)(params)
        else:
            _ = self.locale.translate
            self.settings["page_title"] = _("Transaction list")
            self.bismuth_vars['transactions'] = self.bismuth.latest_transactions(10, for_display=True)
            self.render("transactions.html", bismuth=self.bismuth_vars)

    async def post(self, command=''):
        """
        :return:
        """
        command, *params = command.split('/')
        if command:
            await getattr(self, command)(params)


class JsonHandler(BaseHandler):
    async def get(self, command=''):
        """
        :return:
        """
        params = None
        if '/' in command:
            command, *params = command.split('/')
        # have a list of valid commands for the bismuthclient, and route some to our internal vars
        # The list could also enforce the required number of params.
        if command.startswith('bismuth.'):
            # internal var wallet, config, ....
            command, var = command.split('.')
            json_result = json.dumps(self.bismuth_vars.get(var, None))
        elif command.startswith('settings.'):
            # internal var wallet, config, ....
            command, var = command.split('.')
            json_result = json.dumps(self.settings.get(var, None))
        # TODO: add slug. for cristals
        else:
            try:
                json_result = json.dumps(self.bismuth.command(command, params))
            except Exception as e:
                json_result = json.dumps(str(e))
                # TODO: wrap in a common "error" json structure
        self.write(json_result)
        self.set_header('Content-Type', 'application/json')
        # self.render("home.html", balance="json", wallet_servers=json_result)
        self.finish()


class WalletHandler(BaseHandler):
    """Wallet related routes"""
    async def load(self, params=None):
        if not params:
            wallets = self.bismuth.list_wallets('wallets')
            self.render("wallet_load.html", wallets=wallets, bismuth=self.bismuth_vars)
        else:
            # load a wallet
            file_name = '/'.join(params)
            self.bismuth.load_wallet(file_name)
            # TODO: store as cookie
            self.set_cookie('wallet', file_name)
            self.redirect("/wallet/info")

    async def info(self, params=None):
        wallet_info = self.bismuth.wallet('wallets')
        self.render("wallet_info.html", wallet=wallet_info, bismuth=self.bismuth_vars)

    async def create(self, params=None):
        # self.write(json.dumps(self.request))
        _, param = self.request.uri.split("?")
        _ = self.locale.translate
        wallet = param.replace('wallet=', '')
        wallet = wallet.replace('.der', '')  # just in case the user added .der
        file_name = 'wallets/{}.der'.format(wallet)
        if os.path.isfile(file_name):
            self.render("message.html", type="warning", title=_("Error"), message=_("This file already exists: {}.der").format(wallet), bismuth=self.bismuth_vars)
        else:
            # create one
            if self.bismuth.new_wallet(file_name):
                # load the new wallet
                self.bismuth.load_wallet(file_name)
                self.set_cookie('wallet', file_name)
                self.redirect("/wallet/info")
            else:
                self.render("message.html", type="warning", title=_("Error"), message=_("Error creating {}.der").format(wallet), bismuth=self.bismuth_vars)

    async def get(self, command=''):
        command, *params = command.split('/')
        await getattr(self, command)(params)


class AboutHandler(BaseHandler):

    async def credits(self, params=None):
        self.render("about_credits.html", bismuth=self.bismuth_vars)

    async def network(self, params=None):
        self.render("about_network.html", bismuth=self.bismuth_vars)

    async def get(self, command=''):
        command, *params = command.split('/')
        if not command:
            command = 'credits'
        await getattr(self, command)(params)


class TokensHandler(BaseHandler):
    """Handler for tokens related features"""

    async def list(self, params=None):
        self.render("tokens_list.html", bismuth=self.bismuth_vars)

    async def get(self, command=''):
        command, *params = command.split('/')
        if not command:
            command = 'list'
        await getattr(self, command)(params)


class CristalsHandler(BaseHandler):

    async def list(self, params=None):
        self.render("cristals_list.html", bismuth=self.bismuth_vars)

    async def get(self, command=''):
        command, *params = command.split('/')
        if not command:
            command = 'list'
        await getattr(self, command)(params)


class AddressHandler(BaseHandler):

    async def get(self, command=''):
        self.render("wip.html", bismuth=self.bismuth_vars)


class SearchHandler(BaseHandler):

    async def get(self, command=''):
        self.render("wip.html", bismuth=self.bismuth_vars)


class MessagesHandler(BaseHandler):

    async def get(self, command=''):
        self.render("wip.html", bismuth=self.bismuth_vars)


class TxModule(tornado.web.UIModule):
    def render(self, tx):
        return self.render_string("modules/transaction.html", tx=tx)


async def main():
    tornado.options.parse_command_line()
    app = Application()
    app.listen(options.port)
    # In this demo the server will simply run until interrupted
    # with Ctrl-C, but if you want to shut down more gracefully,
    # call shutdown_event.set().
    shutdown_event = tornado.locks.Event()
    await shutdown_event.wait()


if __name__ == "__main__":
    # See http://www.lexev.org/en/2015/tornado-internationalization-and-localization/
    tornado.locale.load_gettext_translations('locale', 'messages')
    tornado.ioloop.IOLoop.current().run_sync(main)
