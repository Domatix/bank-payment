from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    payment_document_id = fields.Many2one(
        'account.payment.document', string='Payment Document', copy=False,
        readonly=True)

    amount_pending_on_receivables = fields.Monetary(
        string='Amount pending on receivables',
        compute='_compute_amount_on_receivables',
        currency_field='company_currency_id'
    )

    @api.depends('payment_document_id', 'payment_order_id')
    def _compute_amount_on_receivables(self):
        for record in self:
            if record.is_invoice():
                if record.type == 'in_invoice':
                    lines = record.line_ids.filtered(
                        lambda r: r.account_internal_type == 'payable')
                    sign = 1
                elif record.type == 'out_invoice':
                    lines = record.line_ids.filtered(
                        lambda r: r.account_internal_type == 'receivable')
                    sign = -1
                else:
                    lines = []
                if record.invoice_payment_state == 'paid':
                    amount = 0
                else:
                    amount = record.amount_total_signed
                    for line in lines:
                        if line.payment_line_ids:
                            amount += sum(line.payment_line_ids.mapped(
                                'amount_currency')) * sign
                        elif line.document_line_ids:
                            amount += sum(line.document_line_ids.mapped(
                                'amount_currency')) * sign
                record.amount_pending_on_receivables = amount
            else:
                record.amount_pending_on_receivables = 0
