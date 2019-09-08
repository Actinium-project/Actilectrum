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

from PyQt5.QtCore import Qt, QItemSelectionModel
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QFont
from PyQt5.QtWidgets import QHeaderView, QMenu

from electrum_ltc.i18n import _
from electrum_ltc.util import format_time, PR_UNPAID, PR_PAID, get_request_status
from electrum_ltc.util import PR_TYPE_ADDRESS, PR_TYPE_LN, PR_TYPE_BIP70
from electrum_ltc.lnutil import lndecode, RECEIVED
from electrum_ltc.bitcoin import COIN
from electrum_ltc import constants

from .util import (MyTreeView, read_QIcon, MONOSPACE_FONT,
                   import_meta_gui, export_meta_gui, pr_icons)



ROLE_REQUEST_TYPE = Qt.UserRole
ROLE_REQUEST_ID = Qt.UserRole + 1


class InvoiceList(MyTreeView):

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
        self.setSortingEnabled(True)
        self.setModel(QStandardItemModel(self))
        self.update()

    def update(self):
        _list = self.parent.wallet.get_invoices()
        self.model().clear()
        self.update_headers(self.__class__.headers)
        for idx, item in enumerate(_list):
            invoice_type = item['type']
            if invoice_type == PR_TYPE_LN:
                key = item['rhash']
                icon_name = 'lightning.png'
            elif invoice_type == PR_TYPE_ADDRESS:
                key = item['address']
                icon_name = 'bitcoin.png'
            elif invoice_type == PR_TYPE_BIP70:
                key = item['id']
                icon_name = 'seal.png'
            else:
                raise Exception('Unsupported type')
            status = item['status']
            status_str = get_request_status(item) # convert to str
            message = item['message']
            amount = item['amount']
            timestamp = item.get('time', 0)
            date_str = format_time(timestamp) if timestamp else _('Unknown')
            amount_str = self.parent.format_amount(amount, whitespaces=True)
            labels = [date_str, message, amount_str, status_str]
            items = [QStandardItem(e) for e in labels]
            self.set_editability(items)
            items[self.Columns.DATE].setIcon(read_QIcon(icon_name))
            items[self.Columns.STATUS].setIcon(read_QIcon(pr_icons.get(status)))
            items[self.Columns.DATE].setData(key, role=ROLE_REQUEST_ID)
            items[self.Columns.DATE].setData(invoice_type, role=ROLE_REQUEST_TYPE)
            self.model().insertRow(idx, items)

        self.selectionModel().select(self.model().index(0,0), QItemSelectionModel.SelectCurrent)
        # sort requests by date
        self.model().sort(self.Columns.DATE)
        # hide list if empty
        if self.parent.isVisible():
            b = self.model().rowCount() > 0
            self.setVisible(b)
            self.parent.invoices_label.setVisible(b)
        self.filter()

    def import_invoices(self):
        import_meta_gui(self.parent, _('invoices'), self.parent.invoices.import_file, self.update)

    def export_invoices(self):
        export_meta_gui(self.parent, _('invoices'), self.parent.invoices.export_file)

    def create_menu(self, position):
        idx = self.indexAt(position)
        item = self.model().itemFromIndex(idx)
        item_col0 = self.model().itemFromIndex(idx.sibling(idx.row(), self.Columns.DATE))
        if not item or not item_col0:
            return
        key = item_col0.data(ROLE_REQUEST_ID)
        request_type = item_col0.data(ROLE_REQUEST_TYPE)
        assert request_type in [PR_TYPE_ADDRESS, PR_TYPE_BIP70, PR_TYPE_LN]
        column = idx.column()
        column_title = self.model().horizontalHeaderItem(column).text()
        column_data = item.text()
        menu = QMenu(self)
        if column_data:
            if column == self.Columns.AMOUNT:
                column_data = column_data.strip()
            menu.addAction(_("Copy {}").format(column_title), lambda: self.parent.app.clipboard().setText(column_data))
        if request_type in [PR_TYPE_BIP70, PR_TYPE_ADDRESS]:
            self.create_menu_bitcoin_payreq(menu, key)
        elif request_type == PR_TYPE_LN:
            self.create_menu_ln_payreq(menu, key)
        menu.exec_(self.viewport().mapToGlobal(position))

    def create_menu_bitcoin_payreq(self, menu, payreq_key):
        #status = self.parent.wallet.get_invoice_status(payreq_key)
        menu.addAction(_("Details"), lambda: self.parent.show_invoice(payreq_key))
        #if status == PR_UNPAID:
        menu.addAction(_("Pay Now"), lambda: self.parent.do_pay_invoice(payreq_key))
        menu.addAction(_("Delete"), lambda: self.parent.delete_invoice(payreq_key))

    def create_menu_ln_payreq(self, menu, payreq_key):
        req = self.parent.wallet.lnworker.invoices[payreq_key][0]
        menu.addAction(_("Copy Lightning invoice"), lambda: self.parent.do_copy('Lightning invoice', req))
        menu.addAction(_("Delete"), lambda: self.parent.delete_invoice(payreq_key))
