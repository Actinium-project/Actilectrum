from typing import Callable, TYPE_CHECKING, Optional, Union

from kivy.app import App
from kivy.factory import Factory
from kivy.properties import ObjectProperty
from kivy.lang import Builder
from decimal import Decimal
from kivy.clock import Clock

from electrum_ltc.util import InvalidPassword
from electrum_ltc.gui.kivy.i18n import _

if TYPE_CHECKING:
    from ...main_window import ElectrumWindow
    from electrum_ltc.wallet import Abstract_Wallet
    from electrum_ltc.storage import WalletStorage

Builder.load_string('''

<PasswordDialog@Popup>
    id: popup
    title: 'Electrum-LTC'
    message: ''
    BoxLayout:
        size_hint: 1, 1
        orientation: 'vertical'
        Widget:
            size_hint: 1, 0.05
        Label:
            font_size: '20dp'
            text: root.message
            text_size: self.width, None
            size: self.texture_size
        Widget:
            size_hint: 1, 0.05
        Label:
            id: a
            font_size: '50dp'
            text: '*'*len(kb.password) + '-'*(6-len(kb.password))
            size: self.texture_size
        Widget:
            size_hint: 1, 0.05
        GridLayout:
            id: kb
            size_hint: 1, None
            height: self.minimum_height
            update_amount: popup.update_password
            password: ''
            on_password: popup.on_password(self.password)
            spacing: '2dp'
            cols: 3
            KButton:
                text: '1'
            KButton:
                text: '2'
            KButton:
                text: '3'
            KButton:
                text: '4'
            KButton:
                text: '5'
            KButton:
                text: '6'
            KButton:
                text: '7'
            KButton:
                text: '8'
            KButton:
                text: '9'
            KButton:
                text: 'Clear'
            KButton:
                text: '0'
            KButton:
                text: '<'
''')


class PasswordDialog(Factory.Popup):

    def init(self, app: 'ElectrumWindow', *,
             wallet: Union['Abstract_Wallet', 'WalletStorage'] = None,
             msg: str, on_success: Callable = None, on_failure: Callable = None,
             is_change: int = 0):
        self.app = app
        self.wallet = wallet
        self.message = msg
        self.on_success = on_success
        self.on_failure = on_failure
        self.ids.kb.password = ''
        self.success = False
        self.is_change = is_change
        self.pw = None
        self.new_password = None
        self.title = 'Electrum-LTC' + ('  -  ' + self.wallet.basename() if self.wallet else '')

    def check_password(self, password):
        if self.is_change > 1:
            return True
        try:
            self.wallet.check_password(password)
            return True
        except InvalidPassword as e:
            return False

    def on_dismiss(self):
        if not self.success:
            if self.on_failure:
                self.on_failure()
            else:
                # keep dialog open
                return True
        else:
            if self.on_success:
                args = (self.pw, self.new_password) if self.is_change else (self.pw,)
                Clock.schedule_once(lambda dt: self.on_success(*args), 0.1)

    def update_password(self, c):
        kb = self.ids.kb
        text = kb.password
        if c == '<':
            text = text[:-1]
        elif c == 'Clear':
            text = ''
        else:
            text += c
        kb.password = text

    def on_password(self, pw):
        if len(pw) == 6:
            if self.check_password(pw):
                if self.is_change == 0:
                    self.success = True
                    self.pw = pw
                    self.message = _('Please wait...')
                    self.dismiss()
                elif self.is_change == 1:
                    self.pw = pw
                    self.message = _('Enter new PIN')
                    self.ids.kb.password = ''
                    self.is_change = 2
                elif self.is_change == 2:
                    self.new_password = pw
                    self.message = _('Confirm new PIN')
                    self.ids.kb.password = ''
                    self.is_change = 3
                elif self.is_change == 3:
                    self.success = pw == self.new_password
                    self.dismiss()
            else:
                self.app.show_error(_('Wrong PIN'))
                self.ids.kb.password = ''
