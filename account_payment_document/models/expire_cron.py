from odoo import models, fields, _
from datetime import timedelta


class ExpireOrderCron(models.Model):
    _name = "expire.order.cron"
    _description = "Cron to reconcile payments on expiration orders"

    def revision_over_due_orders(self):
        # today = fields.Date.today() + timedelta(days=63)
        today = fields.Date.today()
        overdue_payment_orders = self.env['account.payment.order'].search([
            ('date_prefered', '!=', 'now'),
            ('state', '=', 'uploaded'),
        ])
        for order in overdue_payment_orders:
            if order.only_move_lines:
                if order.date_prefered == 'fixed' and\
                 order.date_scheduled <= today:
                    order.bank_line_ids.reconcile_payment_lines()
                    order.action_done()
                elif order.date_prefered == 'due':
                    blines = order.bank_line_ids
                    for bline in blines:
                        if bline.date <= today and not all(
                            bline.mapped('payment_line_ids').mapped(
                                'move_line_id').mapped('reconciled')):
                            bline.reconcile_payment_lines()
                    if all([mline for mline in order.mapped(
                        'bank_line_ids').mapped('payment_line_ids').mapped(
                            'move_line_id').mapped('reconciled')]):
                        order.action_done()
            else:
                if all([mline for mline in order.bank_line_ids.mapped(
                    'payment_line_ids').mapped('move_line_id').mapped(
                        'reconciled')]):
                    order.action_done()


class ExpireDocumentCron(models.Model):
    _name = "expire.document.cron"
    _description = "Cron to reconcile payments on expiration document"

    def revision_over_due_documents(self):
        # today = fields.Date.today() + timedelta(days=53)
        today = fields.Date.today()
        overdue_payment_docs = self.env['account.payment.document'].search([
            ('date_due', '<=', today),
            ('state', 'in', ['advanced', 'open']),
        ])
        for doc in overdue_payment_docs:
            if doc.payment_type == 'outbound':
                name = _('Expired Payment document %s') % doc.name
            else:
                name = _('Expired Debit document %s') % doc.name
            vals = {
                'journal_id': doc.expiration_move_journal_id.id,
                'ref': name,
                'line_ids': [],
            }
            debit_account_id = doc.document_due_move_account_id.id
            credit_account_id = False
            if doc.payment_order_id.payment_mode_id.offsetting_account == \
                    'bank_account':
                credit_account_id = doc.payment_order_id.journal_id.\
                    default_debit_account_id.id
            elif doc.payment_order_id.payment_mode_id.offsetting_account == \
                    'transfer_account':
                credit_account_id = doc.payment_order_id.payment_mode_id.\
                    transfer_account_id.id
            if debit_account_id and credit_account_id:
                for move in doc.move_ids:
                    reconciled_account = move.line_ids.mapped(
                        'account_id').filtered(
                            lambda r: r.id == credit_account_id)
                    reconciled_line = move.line_ids.filtered(
                        lambda r: r.account_id.id == reconciled_account.id)
                    currency_id = False
                    amount_currency = False
                    if reconciled_line:
                        currency_id = reconciled_line[0].currency_id
                        amount_currency = reconciled_line[0].amount_currency

                    total_debit = sum(line.debit for line in move.line_ids)
                    total_credit = sum(line.credit for line in move.line_ids)
                    debit_line = {
                            'name': name,
                            'partner_id': doc.partner_id.id,
                            'account_id': debit_account_id,
                            'credit': 0,
                            'debit': total_debit,
                            'currency_id': currency_id.id if currency_id
                            else False,
                            'amount_currency': amount_currency.id
                            if amount_currency else False,

                    }
                    credit_line = {
                            'name': name,
                            'partner_id': doc.partner_id.id,
                            'account_id': credit_account_id,
                            'credit': total_credit,
                            'debit': 0,
                            'currency_id': currency_id.id if currency_id
                            else False,
                            'amount_currency': amount_currency.id
                            if amount_currency else False,

                    }
                vals['line_ids'].append((0, 0, debit_line))
                vals['line_ids'].append((0, 0, credit_line))
                move = self.env['account.move'].create(vals)
                doc.action_paid()
                doc.expiration_move_id = move.id
                if doc.payment_mode_id.post_move:
                    move.post()
                for line in doc.document_line_ids:
                    lines_to_rec = line.move_line_id
                    transit_mlines = doc.move_ids.mapped('line_ids').filtered(
                        lambda r: r.document_line_id.id == line.id)
                    assert len(transit_mlines) == 1,\
                        'We should have only 1 move'
                    lines_to_rec |= transit_mlines
                    lines_to_rec.reconcile()
