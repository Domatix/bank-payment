from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class AccountPaymentDocument(models.Model):
    _name = 'account.payment.document'
    _description = 'Payment Document'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(
        string='Name', readonly=False, required=True)

    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        readonly=True,
        states={'draft': [('readonly', False)], 'sent': [('readonly', False)]},
        required=True,
        index=True,
        track_visibility='always',
    )

    payment_order_id = fields.Many2one(
        comodel_name='account.payment.order',
        copy=False,
        string='Related payment order')

    payment_mode_id = fields.Many2one(
        'account.payment.mode', 'Payment Mode', required=True,
        ondelete='restrict', track_visibility='onchange',
        readonly=True, states={'draft': [('readonly', False)]})

    payment_method_id = fields.Many2one(
        'account.payment.method', related='payment_mode_id.payment_method_id',
        readonly=True, store=True)

    payment_type = fields.Selection([
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
        ], string='Payment Type', readonly=True, required=True)

    company_id = fields.Many2one(
        related='payment_mode_id.company_id', store=True, readonly=True)

    company_currency_id = fields.Many2one(
        related='payment_mode_id.company_id.currency_id', store=True,
        readonly=True)

    bank_account_link = fields.Selection(
        related='payment_mode_id.bank_account_link', readonly=True)

    allowed_journal_ids = fields.Many2many(
        comodel_name='account.journal',
        compute="_compute_allowed_journal_ids",
        string="Allowed journals",
    )

    journal_id = fields.Many2one(
        'account.journal', string='Journal', ondelete='restrict',
        readonly=True, states={'draft': [('readonly', False)]},
        track_visibility='onchange')

    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('open', 'Confirmed'),
            ('advanced', 'Advanced'),
            ('paid', 'Paid'),
            ('unpaid', 'Unpaid'),
            ('cancel', 'Cancel'),
        ], string='Status', readonly=True, copy=False, default='draft',
        track_visibility='onchange')

    date_prefered = fields.Selection([
        ('now', 'Immediately'),
        ('due', 'Due Date'),
        ], string='Payment Due Date Type', required=True, default='due',
        track_visibility='onchange', readonly=True,
        states={'draft': [('readonly', False)]})

    date_due = fields.Date(
        string='Payment Due Date', readonly=True,
        states={'draft': [('readonly', False)]}, track_visibility='onchange',
        help="Select a date if you selected 'Due Date' "
        "as the Payment Due Date Type.")

    date_paid = fields.Date(string='Paid Date', readonly=True)

    date = fields.Date(string='Date')

    document_line_ids = fields.One2many(
        'account.document.line', 'document_id', string='Transaction Lines',
        readonly=True, states={'draft': [('readonly', False)]})

    total_company_currency = fields.Monetary(
        compute='_compute_total', store=True, readonly=True,
        currency_field='company_currency_id')

    move_ids = fields.One2many(
        'account.move', 'payment_document_id', string='Journal Entries',
        readonly=True)

    description = fields.Char()

    document_due_move_account_id = fields.Many2one(
        'account.account',
        'Debit default account for account moves for expiration',
        readonly=True,
        states={'draft': [('readonly', False)]}
    )

    expiration_move_journal_id = fields.Many2one(
        'account.journal', string='Expiration Move Journal',
        ondelete='restrict', readonly=True,
        states={'draft': [('readonly', False)]},
        track_visibility='onchange')

    expiration_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Expiration Account Move')

    def copy(self, default=None):
        default = dict(default or {})
        if "name" not in default or\
                ("name" in default and not default["name"]):
            default["name"] = self.name + " (copia)"
        return super(AccountPaymentDocument, self).copy(default)

    @api.depends('payment_mode_id')
    def _compute_allowed_journal_ids(self):
        for record in self:
            if record.payment_mode_id.bank_account_link == 'fixed':
                record.allowed_journal_ids = (
                    record.payment_mode_id.fixed_journal_id)
            elif record.payment_mode_id.bank_account_link == 'variable':
                record.allowed_journal_ids = (
                    record.payment_mode_id.variable_journal_ids)
            else:
                record.allowed_journal_ids = False

    @api.depends(
        'document_line_ids', 'document_line_ids.amount_company_currency')
    def _compute_total(self):
        for rec in self:
            rec.total_company_currency = sum(
                rec.mapped('document_line_ids.amount_company_currency') or
                [0.0])

    def unlink(self):
        for document in self:
            if document.state != 'draft':
                raise UserError(_(
                    "You cannot delete a non draft payment document. You can "
                    "cancel it in order to do so."))
        return super(AccountPaymentDocument, self).unlink()

    @api.constrains('payment_type', 'payment_mode_id')
    def payment_document_constraints(self):
        for document in self:
            if (
                    document.payment_mode_id.payment_type and
                    document.payment_mode_id.payment_type !=
                    document.payment_type):
                raise ValidationError(_(
                    "The payment type (%s) is not the same as the payment "
                    "type of the payment mode (%s)") % (
                        document.payment_type,
                        document.payment_mode_id.payment_type))

    @api.constrains('date_due')
    def check_date_due(self):
        today = fields.Date.context_today(self)
        for document in self:
            if document.date_due:
                if document.date_due < today:
                    raise ValidationError(_(
                        "On payment document %s, the Payment Due Date "
                        "is in the past (%s).")
                        % (document.name, document.date_due))

    @api.model
    def create(self, vals):
        if not vals.get('date'):
            vals['date'] = fields.Date.context_today(self)
        if vals.get('payment_mode_id'):
            payment_mode = self.env['account.payment.mode'].browse(
                vals['payment_mode_id'])
            vals['payment_type'] = payment_mode.payment_type
            if payment_mode.bank_account_link == 'fixed':
                vals['journal_id'] = payment_mode.fixed_journal_id.id
            if (
                    not vals.get('date_prefered') and
                    payment_mode.default_date_prefered and
                    payment_mode.default_date_prefered != 'fixed'):
                vals['date_prefered'] = payment_mode.default_date_prefered
            else:
                vals['date_prefered'] = 'due'
        return super(AccountPaymentDocument, self).create(vals)

    @api.onchange('payment_mode_id')
    def payment_mode_id_change(self):
        if len(self.allowed_journal_ids) == 1:
            self.journal_id = self.allowed_journal_ids
        if (
                self.payment_mode_id.default_date_prefered and
                self.payment_mode_id.default_date_prefered != 'fixed'):
            self.date_prefered = self.payment_mode_id.default_date_prefered
        else:
            self.date_prefered = 'due'

    def action_paid(self):
        self.write({
            'date_paid': fields.Date.context_today(self),
            'state': 'paid',
            })
        return True

    def action_unpaid(self):
        self.write({
            'state': 'unpaid',
            })
        return True

    def action_paid_cancel(self):
        for move in self.move_ids:
            move.button_cancel()
            for move_line in move.line_ids:
                move_line.remove_move_reconcile()
            move.unlink()
        self.action_cancel()
        return True

    def action_cancel(self):
        for document in self:
            document.write({'state': 'cancel'})
        return True

    def cancel2draft(self):
        self.write({'state': 'draft'})
        return True

    def open2advanced(self):
        self.write({'state': 'advanced'})
        return True

    def draft2open(self):
        for document in self:
            if not document.journal_id:
                raise UserError(_(
                    'Missing Journal on payment document %s.') % document.name)
            if (
                    document.payment_method_id.bank_account_required and
                    not document.journal_id.bank_account_id):
                raise UserError(_(
                    "Missing bank account on journal '%s'.")
                    % document.journal_id.display_name)
            if not document.document_line_ids:
                raise UserError(_(
                    'There are no transactions on payment document %s.')
                    % document.name)

            document.recompute()
            if document.payment_mode_id.generate_move:
                document.generate_move()
        self.write({'state': 'open'})
        return True

    def _create_reconcile_move(self):
        self.ensure_one()
        post_move = self.payment_mode_id.post_move
        am_obj = self.env['account.move']
        mvals = self._prepare_move()
        move = am_obj.create(mvals)
        if post_move:
            move.post()

    def generate_move(self):
        """
        Create the moves that 'pay off' the move lines from
        the payment/debit document.
        """
        self.ensure_one()
        self._create_reconcile_move()

    def _prepare_move(self):
        if self.payment_type == 'outbound':
            ref = _('Payment document %s') % self.name
        else:
            ref = _('Debit document %s') % self.name
        if self.payment_mode_id.offsetting_account == 'bank_account':
            journal_id = self.journal_id.id
        elif self.payment_mode_id.offsetting_account == 'transfer_account':
            journal_id = self.payment_mode_id.transfer_journal_id.id
        vals = {
            'journal_id': journal_id,
            'ref': ref,
            'payment_document_id': self.id,
            'line_ids': [],
            }
        total_company_currency = total_payment_currency = 0
        for doc_line in self.document_line_ids:
            total_company_currency += doc_line.amount_company_currency
            total_payment_currency += doc_line.amount_currency
            partner_ml_vals = self._prepare_move_line_partner_account(doc_line)
            vals['line_ids'].append((0, 0, partner_ml_vals))

        trf_ml_vals = self._prepare_move_line_offsetting_account(
            total_company_currency, total_payment_currency)
        vals['line_ids'].append((0, 0, trf_ml_vals))
        return vals

    def _prepare_move_line_partner_account(self, doc_line):
        if doc_line.move_line_id:
            account_id = doc_line.move_line_id.account_id.id
        else:
            if self.payment_type == 'inbound':
                account_id =\
                    doc_line.partner_id.property_account_receivable_id.id
            else:
                account_id =\
                    doc_line.partner_id.property_account_payable_id.id
        if self.payment_type == 'outbound':
            name = _('Payment document line %s') % doc_line.move_line_id.name
        else:
            name = _('Debit document line %s') % doc_line.move_line_id.name
        vals = {
            'name': name,
            'partner_id': doc_line.partner_id.id,
            'document_line_id': doc_line.id,
            'account_id': account_id,
            'credit': (self.payment_type == 'inbound' and
                       doc_line.amount_company_currency or 0.0),
            'debit': (self.payment_type == 'outbound' and
                      doc_line.amount_company_currency or 0.0),
            }

        if doc_line.currency_id != doc_line.company_currency_id:
            sign = self.payment_type == 'inbound' and -1 or 1
            vals.update({
                'currency_id': doc_line.currency_id.id,
                'amount_currency': doc_line.amount_currency * sign,
                })
        return vals

    def _prepare_move_line_offsetting_account(
            self, amount_company_currency, amount_payment_currency):
        vals = {}
        if self.payment_type == 'outbound':
            name = _('Payment document %s') % self.name
        else:
            name = _('Debit document %s') % self.name
        if self.payment_mode_id.offsetting_account == 'bank_account':
            vals.update({'date': self.date})
        else:
            if self.date_prefered == 'due':
                vals.update({'date_maturity': self.date_due})
            else:
                vals.update({'date_maturity': self.date})

        if self.payment_mode_id.offsetting_account == 'bank_account':
            account_id = self.journal_id.default_debit_account_id.id
        elif self.payment_mode_id.offsetting_account == 'transfer_account':
            account_id = self.payment_mode_id.transfer_account_id.id
        partner_id = self.partner_id.id
        vals.update({
            'name': name,
            'partner_id': partner_id,
            'account_id': account_id,
            'credit': (self.payment_type == 'outbound' and
                       amount_company_currency or 0.0),
            'debit': (self.payment_type == 'inbound' and
                      amount_company_currency or 0.0),
        })
        if (
                self.document_line_ids[0].currency_id !=
                self.document_line_ids[0].company_currency_id):
            sign = self.payment_type == 'outbound' and -1 or 1
            vals.update({
                'currency_id': self.document_line_ids[0].currency_id.id,
                'amount_currency': amount_payment_currency * sign,
                })
        return vals
