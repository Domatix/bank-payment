from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    document_line_ids = fields.One2many(
        comodel_name='account.document.line',
        inverse_name='move_line_id',
        string="Document lines",
    )

    document_line_id = fields.Many2one(
        comodel_name='account.document.line',
        string='Transaction')

    def _prepare_document_line_vals(self, document):
        self.ensure_one()
        assert document, 'Missing payment document'
        aplo = self.env['account.document.line']
        # default values for communication_type and communication
        communication_type = 'normal'
        communication = self.move_id.ref or self.move_id.name
        # change these default values if move line is linked to an invoice
        if self.move_id.is_invoice():
            if self.move_id.reference_type != 'none':
                communication = self.move_id.ref
                ref2comm_type =\
                    aplo.invoice_reference_type2communication_type()
                communication_type =\
                    ref2comm_type[self.move_id.reference_type]
            else:
                if (
                        self.move_id.type in ('in_invoice', 'in_refund') and
                        self.move_id.ref
                ):
                    communication = self.move_id.ref
                elif 'out' in self.move_id.type:
                    # Force to only put invoice number here
                    communication = self.move_id.name
        if self.currency_id:
            currency_id = self.currency_id.id
            amount_currency = self.amount_residual_currency
        else:
            currency_id = self.company_id.currency_id.id
            amount_currency = self.amount_residual
            # TODO : check that self.amount_residual_currency is 0
            # in this case
        if document.payment_type == 'outbound':
            amount_currency *= -1
        vals = {
            'document_id': document.id,
            'partner_id': self.partner_id.id,
            'move_line_id': self.id,
            'communication': communication,
            'communication_type': communication_type,
            'currency_id': currency_id,
            'amount_currency': amount_currency,
            # date is set when the user confirms the payment document
            }
        return vals

    def create_document_line_from_move_line(self, document):
        vals_list = []
        for mline in self:
            vals_list.append(mline._prepare_document_line_vals(document))
        return self.env['account.document.line'].create(vals_list)
