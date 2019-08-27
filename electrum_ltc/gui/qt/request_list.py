#!/usr/bin/env python
#
# Electrum - lightweight Bitcoin client
# Copyright (C) 2015 Thomas Voegtlin
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from enum import IntEnum

from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtWidgets import QMenu, QHeaderView
from PyQt5.QtCore import Qt, QItemSelectionModel

from electrum_ltc.i18n import _
from electrum_ltc.util import format_time, age, get_request_status
from electrum_ltc.util import PR_UNPAID, PR_EXPIRED, PR_PAID, PR_UNKNOWN, PR_INFLIGHT, pr_tooltips
from electrum_ltc.lnutil import SENT, RECEIVED
from electrum_ltc.plugin import run_hook
from electrum_ltc.wallet import InternalAddressCorruption
from electrum_ltc.bitcoin import COIN
from electrum_ltc.lnaddr import lndecode
import electrum_ltc.constants as constants

from .util import MyTreeView, pr_icons, read_QIcon

REQUEST_TYPE_BITCOIN = 0
REQUEST_TYPE_LN = 1

ROLE_REQUEST_TYPE = Qt.UserRole
ROLE_RHASH_OR_ADDR = Qt.UserRole + 1

class RequestList(MyTreeView):

    class Columns(IntEnum):
        DATE = 0
        DESCRIPTION = 1
        AMOUNT = 2
        STATUS = 3

    headers = {
        Columns.DATE: _('Date'),
        Columns.DESCRIPTION: _('Description'),
        Columns.AMOUNT: _('Amount'),
        Columns.STATUS: _('Status'),
    }
    filter_columns = [Columns.DATE, Columns.DESCRIPTION, Columns.AMOUNT]

    def __init__(self, parent):
        super().__init__(parent, self.create_menu,
                         stretch_column=self.Columns.DESCRIPTION,
                         editable_columns=[])
        self.setModel(QStandardItemModel(self))
        self.setSortingEnabled(True)
        self.update()
        self.selectionModel().currentRowChanged.connect(self.item_changed)

    def select_key(self, key):
        for i in range(self.model().rowCount()):
            item = self.model().index(i, self.Columns.DATE)
            row_key = item.data(ROLE_RHASH_OR_ADDR)
            if key == row_key:
                self.selectionModel().setCurrentIndex(item, QItemSelectionModel.SelectCurrent | QItemSelectionModel.Rows)
                break

    def item_changed(self, idx):
        # TODO use siblingAtColumn when min Qt version is >=5.11
        item = self.model().itemFromIndex(idx.sibling(idx.row(), self.Columns.DATE))
        request_type = item.data(ROLE_REQUEST_TYPE)
        key = item.data(ROLE_RHASH_OR_ADDR)
        is_lightning = request_type == REQUEST_TYPE_LN
        req = self.wallet.get_request(key, is_lightning)
        if req is None:
            self.update()
            return
        text = req.get('invoice') if is_lightning else req.get('URI')
        self.parent.receive_address_e.setText(text)

    def refresh_status(self):
        m = self.model()
        for r in range(m.rowCount()):
            idx = m.index(r, self.Columns.STATUS)
            date_idx = idx.sibling(idx.row(), self.Columns.DATE)
            date_item = m.itemFromIndex(date_idx)
            status_item = m.itemFromIndex(idx)
            key = date_item.data(ROLE_RHASH_OR_ADDR)
            is_lightning = date_item.data(ROLE_REQUEST_TYPE) == REQUEST_TYPE_LN
            req = self.wallet.get_request(key, is_lightning)
            if req:
                status_str = get_request_status(req)
                status_item.setText(status_str)
                status_item.setIcon(read_QIcon(pr_icons.get(req['status'])))

    def update(self):
        self.wallet = self.parent.wallet
        domain = self.wallet.get_receiving_addresses()
        self.parent.update_receive_address_styling()
        self.model().clear()
        self.update_headers(self.__class__.headers)
        for req in self.wallet.get_sorted_requests(self.config):
            status = req.get('status')
            if status == PR_PAID:
                continue
            request_type = REQUEST_TYPE_LN if req.get('lightning', False) else REQUEST_TYPE_BITCOIN
            timestamp = req.get('time', 0)
            amount = req.get('amount')
            message = req['memo']
            date = format_time(timestamp)
            amount_str = self.parent.format_amount(amount) if amount else ""
            status_str = get_request_status(req)
            labels = [date, message, amount_str, status_str]
            items = [QStandardItem(e) for e in labels]
            self.set_editability(items)
            items[self.Columns.DATE].setData(request_type, ROLE_REQUEST_TYPE)
            items[self.Columns.STATUS].setIcon(read_QIcon(pr_icons.get(status)))
            if request_type == REQUEST_TYPE_LN:
                items[self.Columns.DATE].setData(req['rhash'], ROLE_RHASH_OR_ADDR)
                items[self.Columns.DATE].setIcon(read_QIcon("lightning.png"))
                items[self.Columns.DATE].setData(REQUEST_TYPE_LN, ROLE_REQUEST_TYPE)
            else:
                address = req['address']
                if address not in domain:
                    continue
                expiration = req.get('exp', None)
                signature = req.get('sig')
                requestor = req.get('name', '')
                items[self.Columns.DATE].setData(address, ROLE_RHASH_OR_ADDR)
                if signature is not None:
                    items[self.Columns.DATE].setIcon(read_QIcon("seal.png"))
                    items[self.Columns.DATE].setToolTip(f'signed by {requestor}')
                else:
                    items[self.Columns.DATE].setIcon(read_QIcon("bitcoin.png"))
            self.model().insertRow(self.model().rowCount(), items)
        self.filter()
        # sort requests by date
        self.model().sort(self.Columns.DATE)
        # hide list if empty
        if self.parent.isVisible():
            b = self.model().rowCount() > 0
            self.setVisible(b)
            self.parent.receive_requests_label.setVisible(b)

    def create_menu(self, position):
        idx = self.indexAt(position)
        item = self.model().itemFromIndex(idx)
        # TODO use siblingAtColumn when min Qt version is >=5.11
        item = self.model().itemFromIndex(idx.sibling(idx.row(), self.Columns.DATE))
        if not item:
            return
        addr = item.data(ROLE_RHASH_OR_ADDR)
        request_type = item.data(ROLE_REQUEST_TYPE)
        assert request_type in [REQUEST_TYPE_BITCOIN, REQUEST_TYPE_LN]
        if request_type == REQUEST_TYPE_BITCOIN:
            req = self.wallet.receive_requests.get(addr)
        elif request_type == REQUEST_TYPE_LN:
            req = self.wallet.lnworker.invoices[addr][0]
        if req is None:
            self.update()
            return
        column = idx.column()
        column_title = self.model().horizontalHeaderItem(column).text()
        column_data = self.model().itemFromIndex(idx).text()
        menu = QMenu(self)
        if column == self.Columns.AMOUNT:
            column_data = column_data.strip()
        menu.addAction(_("Copy {}").format(column_title), lambda: self.parent.do_copy(column_title, column_data))
        if request_type == REQUEST_TYPE_BITCOIN:
            self.create_menu_bitcoin_payreq(menu, addr)
        elif request_type == REQUEST_TYPE_LN:
            self.create_menu_ln_payreq(menu, addr, req)
        menu.exec_(self.viewport().mapToGlobal(position))

    def create_menu_bitcoin_payreq(self, menu, addr):
        menu.addAction(_("Copy Address"), lambda: self.parent.do_copy('Address', addr))
        menu.addAction(_("Copy URI"), lambda: self.parent.do_copy('URI', self.wallet.get_request_URI(addr)))
        menu.addAction(_("Save as BIP70 file"), lambda: self.parent.export_payment_request(addr))
        menu.addAction(_("Delete"), lambda: self.parent.delete_payment_request(addr))
        run_hook('receive_list_menu', menu, addr)

    def create_menu_ln_payreq(self, menu, payreq_key, req):
        menu.addAction(_("Copy Lightning invoice"), lambda: self.parent.do_copy('Lightning invoice', req))
        menu.addAction(_("Delete"), lambda: self.parent.delete_lightning_payreq(payreq_key))
