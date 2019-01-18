

import logging
import sys
from tornado.web import RequestHandler
from tornado.template import Loader, Template
from os import path
from modules.i18n import get_spend_type


class BaseHandler(RequestHandler):
    """Common ancestor for ann route handlers"""

    def initialize(self):
        """Common init for every request"""
        # TODO: advantage in using Tornado Babel maybe? https://media.readthedocs.org/pdf/tornado-babel/0.1/tornado-babel.pdf
        _ = self.locale.translate
        self.app_log = logging.getLogger("tornado.application")
        self.bismuth = self.settings['bismuth_client']
        # Load persisted wallet if needed
        wallet = self.get_cookie('wallet')
        """
        if wallet and wallet != self.bismuth.wallet_file:
            self.bismuth.load_wallet(wallet)
        """
        address = self.get_cookie('address')
        if address:
            try:
                self.bismuth.set_address(address)
            except:
                pass
        # print("cookies", self.cookies)
        self.bismuth_vars = self.settings['bismuth_vars']
        # self.bismuth_vars['wallet'] =
        # reflect server info
        self.settings["page_title"] = self.settings["app_title"]
        self.bismuth_vars['server'] = self.bismuth.info()
        self.bismuth_vars['server_status'] = self.bismuth.status()
        self.bismuth_vars['balance'] = self.bismuth.balance(for_display=True)
        self.bismuth_vars['address'] = self.bismuth._wallet.info()['address']  # self.bismuth_vars['server']['address']
        self.bismuth_vars['params'] = {}
        self.bismuth_vars['extra'] = {"header":'', "footer": ''}
        spend_type = self.application.wallet_settings['spend']['type']
        self.bismuth_vars['spend_type'] = {"type": spend_type, "label": get_spend_type(_, spend_type) }
        # print(self.bismuth.wallet())
        self.bismuth_vars['master_set'] = self.bismuth.wallet()['encrypted'] # self.application.wallet_settings['master_hash']
        self.bismuth_vars['wallet_locked'] = self.bismuth._wallet._locked
        self.crystals = self.settings['bismuth_crystals']
        if self.bismuth_vars['address'] is None:
            self.bismuth_vars['address'] = _("No Bismuth address, please create or load a wallet first.")
        self.update_crystals()
        # self.bismuth_vars['dtlanguage'] = get_dt_language(_)

    def update_crystals(self):
        crystals = self.application.crystals_manager.get_loaded_crystals()
        crystal_names = [name.split('_')[1] for name in crystals.keys()]
        self.bismuth_vars['crystals'] = crystal_names

    # This could be static, but its easier to let it there so the template have direct access.
    def bool2str(self, a_boolean, iftrue, iffalse):
        return iftrue if a_boolean else iffalse

    def active_if(self, path: str):
        """return the 'active' string if the request uri is the one in path. Used for menu css"""
        if self.request.uri == path:
            return "active"
        return ''

    def active_if_start(self, path: str):
        """return the 'active' string if the request uri begins with the one in path. Used for menu css"""
        if self.request.uri.startswith(path):
            return "active"
        return ''

    def message(self, title, message, type="info"):
        """Display message template page"""
        self.render("message.html", bismuth=self.bismuth_vars, title=title, message=message, type=type)

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


class CrystalHandler(BaseHandler):
    """Common ancestor for all crystals handlers"""

    def render_string(self, template_name, **kwargs):
        """Generate the given template with the given arguments.

        We return the generated byte string (in utf8). To generate and
        write a template as a response, use render() above.
        """
        if template_name in ['base.html']:
            # exceptions where template is to be loaded from main theme, not crystal.
            template_path = self.application.settings.get("template_path")
        else:
            template_path = self.get_template_path()
        # If no template_path is specified, use the path of the calling file
        # print("render_string", template_name)
        # print("template_path", template_path)
        if not template_path:
            frame = sys._getframe(0)
            web_file = frame.f_code.co_filename
            while frame.f_code.co_filename == web_file:
                frame = frame.f_back
            template_path = path.dirname(frame.f_code.co_filename)
        with RequestHandler._template_loader_lock:
            # print("RequestHandler._template_loaders:", RequestHandler._template_loaders)
            if template_path not in RequestHandler._template_loaders:
                # loader = self.create_template_loader(template_path)
                loader = CrystalLoader(template_path, self.application.settings.get("template_path"))
                RequestHandler._template_loaders[template_path] = loader
            else:
                loader = RequestHandler._template_loaders[template_path]
        # print("RequestHandler._template_loaders:", RequestHandler._template_loaders)
        # print("loader root 1", loader.root)
        t = loader.load(template_name)  # , parent_path=template_path)
        namespace = self.get_template_namespace()
        namespace.update(kwargs)
        return t.generate(**namespace)


class CrystalLoader(Loader):
    """A template loader that loads from several root directory to account for crystals and base template.
    """
    def __init__(self, root_directory, fallback_directory, **kwargs):
        super(Loader, self).__init__(**kwargs)
        self.root = path.abspath(root_directory)
        self.fallback = path.abspath(fallback_directory)
        self.current = self.root
        # print("CrystalLoader path", self.root)

    def resolve_path(self, name, parent_path=None):
        # print("resolve path", name, parent_path)
        my_root = self.root
        if name in ['base.html', 'message.html']:
            # exceptions where template is to be loaded from main theme, not crystal.
            my_root = self.fallback
        # print("resolve path root", my_root)
        self.current = my_root
        if parent_path and not parent_path.startswith("<") and \
            not parent_path.startswith("/") and \
                not name.startswith("/"):
            current_path = path.join(my_root, parent_path)
            file_dir = path.dirname(path.abspath(current_path))
            relative_path = path.abspath(path.join(file_dir, name))
            if relative_path.startswith(my_root):
                name = relative_path[len(my_root) + 1:]
        # print("name", name)
        return name

    def _create_template(self, name):
        # print("_create_template", name, "root", self.current)
        a_path = path.join(self.current, name)
        with open(a_path, "rb") as f:
            template = Template(f.read(), name=name, loader=self)
            return template

