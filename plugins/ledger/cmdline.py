from electrum_ltc.util import print_msg
from .ledger import LedgerPlugin
from ..hw_wallet import CmdLineHandler

class Plugin(LedgerPlugin):
    handler = CmdLineHandler()
    @hook
    def init_keystore(self, keystore):
        if not isinstance(keystore, self.keystore_class):
            return
        keystore.handler = self.handler
