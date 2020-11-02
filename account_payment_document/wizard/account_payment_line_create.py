from odoo import models, fields, api, _


class AccountPaymentLineCreate(models.TransientModel):
    _inherit = 'account.payment.line.create'

    def _prepare_move_line_domain(self):
        domain = super(AccountPaymentLineCreate, self)._prepare_move_line_domain()
        paylines = self.env['account.document.line'].search([
            ('state', 'in', ('draft', 'open', 'advanced')),
            ('move_line_id', '!=', False)])
        if paylines:
            move_lines_ids = [payline.move_line_id.id for payline in paylines]
            domain += [('id', 'not in', move_lines_ids)]
        return domain
