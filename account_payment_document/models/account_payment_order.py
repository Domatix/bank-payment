from odoo import models, fields, api


class AccountPaymentOrder(models.Model):
    _inherit = 'account.payment.order'

    payment_document_ids = fields.One2many(
        comodel_name='account.payment.document',
        inverse_name='payment_order_id',
        string='Received documents',
        readonly=True, states={'draft': [('readonly', False)]})

    partner_ids = fields.Many2many(
        'res.partner',
        string='Partners',
        compute='_compute_partner_ids',
        store=True
    )

    only_docs = fields.Boolean(
        string='Only Payment Documents',
        store=True,
        compute="_computed_only_docs")

    only_move_lines = fields.Boolean(
        string='Only Account Move Lines',
        store=True,
        compute="_computed_move_lines")

    @api.depends('payment_line_ids')
    def _compute_partner_ids(self):
        for record in self:
            record.partner_ids = [
                (6, 0, record.payment_line_ids.mapped('partner_id').ids)]

    @api.depends('payment_line_ids', 'payment_document_ids')
    def _computed_only_docs(self):
        for record in self:
            if record.payment_document_ids:
                record.only_docs = True
            else:
                record.only_docs = False

    @api.depends('payment_line_ids', 'payment_document_ids')
    def _computed_move_lines(self):
        for record in self:
            if record.payment_line_ids and not record.payment_document_ids:
                record.only_move_lines = True
            else:
                record.only_move_lines = False

    def draft2open(self):
        for doc in self.payment_document_ids:
            if doc.payment_mode_id.offsetting_account == 'bank_account':
                account_id = doc.journal_id.default_debit_account_id.id
            elif doc.payment_mode_id.offsetting_account == 'transfer_account':
                account_id = doc.payment_mode_id.transfer_account_id.id
            if account_id:
                move_list = doc.mapped(
                    'move_ids').mapped('line_ids').filtered(
                        lambda r: r.account_id.id == account_id)
                move_list -= self.payment_line_ids.mapped('move_line_id')
                move_list.create_payment_line_from_move_line(
                    doc.payment_order_id)
        return super(AccountPaymentOrder, self).draft2open()

    def _create_reconcile_move(self, hashcode, blines):
        self.ensure_one()
        post_move = self.payment_mode_id.post_move
        am_obj = self.env['account.move']
        mvals = self._prepare_move(blines)
        move = am_obj.create(mvals)
        if self.date_prefered == 'now':
            blines.reconcile_payment_lines()
        if post_move:
            move.post()

    def generated2uploaded(self):
        super(AccountPaymentOrder, self).generated2uploaded()
        for order in self:
            if order.only_docs:
                for line in order.payment_line_ids:
                    lines_to_rec = line.move_line_id
                    lines_to_rec |= order.move_ids.mapped('line_ids').filtered(
                        lambda r: lines_to_rec.id in r.bank_payment_line_id.mapped(
                            'payment_line_ids').mapped('move_line_id').ids)
                    lines_to_rec.reconcile()
        return True
