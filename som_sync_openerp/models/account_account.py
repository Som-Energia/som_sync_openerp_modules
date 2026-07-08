#  -*- coding: utf-8 -*-
import logging

from osv import osv
from service.security import Sudo


logger = logging.getLogger(__name__)


class AccountAccount(osv.osv):
    _name = 'account.account'
    _inherit = 'account.account'

    ODOO_SYNC_NORMALIZED_LENGTH_KEY = 'odoo_sync_account_code_normalized_length'
    ACCOUNT_CODE_PREFIX_LENGTH = 3
    ACCOUNT_CODE_SUFFIX_LENGTH = 3

    MAPPING_FIELDS_TO_SYNC = {
        'name': 'name',
        'code': 'code',
        'id': 'pnt_erp_id',
    }
    MAPPING_FK = {
    }
    MAPPING_CONSTANTS = {
    }

    def get_endpoint_suffix(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        account = self.browse(cr, uid, id, context=context)
        if account.code:
            res = '{}'.format(self._normalize_account_code_for_odoo(
                cr, uid, account.code, context=context
            ))
            return res
        else:
            return False

    def _get_account_code_normalized_length(self, cr, uid, context=None):
        if context is None:
            context = {}
        conf_obj = self.pool.get('res.config')
        value = conf_obj.get(
            cr, uid, self.ODOO_SYNC_NORMALIZED_LENGTH_KEY, ''
        )
        if value in (False, None, ''):
            return False
        try:
            target_length = int(value)
        except (TypeError, ValueError):
            logger.warning(
                'Invalid %s config value: %s',
                self.ODOO_SYNC_NORMALIZED_LENGTH_KEY, value,
            )
            return False
        if target_length <= 0:
            logger.warning(
                'Invalid %s config value: %s',
                self.ODOO_SYNC_NORMALIZED_LENGTH_KEY, value,
            )
            return False
        return target_length

    def _normalize_account_code_for_odoo(self, cr, uid, code, context=None):
        if context is None:
            context = {}
        if not code:
            return code

        target_length = self._get_account_code_normalized_length(
            cr, uid, context=context
        )
        if not target_length:
            return code

        if not isinstance(code, basestring):
            code = str(code)

        if not code.isdigit() or len(code) <= target_length:
            return code

        prefix = code[:self.ACCOUNT_CODE_PREFIX_LENGTH]
        suffix = code[-self.ACCOUNT_CODE_SUFFIX_LENGTH:]
        middle = list(code[
            self.ACCOUNT_CODE_PREFIX_LENGTH:-self.ACCOUNT_CODE_SUFFIX_LENGTH
        ])

        min_length = (
            self.ACCOUNT_CODE_PREFIX_LENGTH + self.ACCOUNT_CODE_SUFFIX_LENGTH
        )
        if target_length < min_length:
            logger.warning(
                'Cannot normalize account code %s to target length %s: '
                'target is shorter than preserved prefix/suffix length',
                code, target_length,
            )
            return code

        extra_chars = len(code) - target_length
        zero_indexes = [index for index, char in enumerate(middle) if char == '0']
        if len(zero_indexes) < extra_chars:
            logger.warning(
                'Cannot normalize account code %s to target length %s '
                'without removing non-zero middle digits',
                code, target_length,
            )
            return code

        indexes_to_remove = set(zero_indexes[:extra_chars])
        normalized_middle = ''.join([
            char for index, char in enumerate(middle)
            if index not in indexes_to_remove
        ])
        return '{}{}{}'.format(prefix, normalized_middle, suffix)

    def hook_last_modifications(self, cr, uid, data, context=None):
        if context is None:
            context = {}
        if 'code' not in data:
            return data
        data['code'] = self._normalize_account_code_for_odoo(
            cr, uid, data.get('code'), context=context
        )
        return data

    def create(self, cr, uid, vals, context=None):
        if context is None:
            context = {}
        ids = super(AccountAccount, self).create(cr, uid, vals, context=context)

        with Sudo(uid=1, gid=0):
            sync_obj = self.pool.get('odoo.sync')
            sync_obj.common_sync_model_create_update(
                cr, uid, self._name, 'create', ids, context=context
            )

        return ids


AccountAccount()
