#  -*- coding: utf-8 -*-
from __future__ import absolute_import
from time import sleep
from osv import osv, fields
from oorq.decorators import job
import requests
from datetime import datetime
from .odoo_exceptions import CreationNotSupportedException, ERPObjectNotExistsException, UpdateNotSupportedException, ForeingKeyNotAvailable  # noqa: E501
import logging

FF_ENABLE_ODOO_SYNC = True  # TODO: as variable in res.config ??

# Mapping of models entities to update erp_id in Odoo: key -> erp model, value -> odoo entity name
MAPPING_MODELS_ENTITIES = {
    'account.account': 'account',
    'res.country.state': 'state',
    'res.country': 'country',
    'res.municipi': 'city',
    'res.partner': 'partner',
    'res.partner.address': 'partner',
    'res.partner.bank': 'bank',
}

STATIC_MODELS = [
    'account.fiscal.position',
    'account.payment.term',
    'payment.type',
    'res.country',
]

# Mapping of models: key -> erp model, value -> odoo endpoint sufix
MAPPING_MODELS_GET = {
    'account.account': 'account',
    'res.country.state': 'state',
    'res.country': 'country',
    'res.municipi': 'city',
    'res.partner': 'partner',
    'res.partner.address': 'partner',
    'res.partner.bank': 'bank',
}

# Mapping of models to post endpoint sufix: key -> erp model, value -> odoo endpoint sufix
MAPPING_MODELS_POST = {
    'account.account': 'accounts',
    'res.country.state': 'states',
    'res.partner': 'partners',
    'res.partner.address': 'partners',
    'res.partner.bank': 'banks',
}

# Mapping of modles to patch
MAPPING_MODELS_PATCH = {
    'res.partner': 'partner',
    'res.partner.address': 'partner',
}


class OdooSync(osv.osv):
    "Sync manager"

    _name = "odoo.sync"
    _description = 'Syncronization manager'

    def _get_conn_params(self, cursor, uid):
        config_obj = self.pool.get('res.config')
        try:
            odoo_url_api = config_obj.get(cursor, uid, 'odoo_url_api', 'http://localhost:8069/api/')
            odoo_api_key = config_obj.get(cursor, uid, 'odoo_api_key', 'secret')
        except Exception:
            raise osv.except_osv('Configuration error',
                                 'Odoo connection parameters not found.')
        return odoo_url_api, odoo_api_key

    def sync_model_enabled(self, cursor, uid, model):
        config_obj = self.pool.get('res.config')
        list_models_to_sync = eval(config_obj.get(cursor, uid, 'odoo_erp_models_to_sync', '[]'))
        if model in list_models_to_sync:
            return True
        return False

    def sync_model_enabled_amplified(self, cursor, uid, model):
        """
            odoo_erp_models_to_sync = [
                {'model': 'account.account', 'auto_sync': True, 'async_enabled': True},
                {'model': 'res.partner', 'auto_sync': False, 'async_enabled': True}]
            auto_sync: sync triggered automatically when create, write or unlink occurs in ERP,
                otherwise sync only on-demand.
            async_enabled: if True, sync is done asynchronously
        """
        config_obj = self.pool.get('res.config')
        dict_models_to_sync = eval(config_obj.get(cursor, uid, 'odoo_erp_models_to_sync', '[]'))
        for dict_model in dict_models_to_sync:
            if dict_model['model'] == model:
                return True, dict_model['auto_sync'], dict_model['async_enabled']
        return False, False, False

    def common_sync_model_create_update(self, cursor, uid, model, ids, action, context={}):
        try:
            sync_enabled, auto_sync, async_enabled = (
                self.sync_model_enabled_amplified(cursor, uid, model))
            if action == 'sync':
                auto_sync = True  # force sync for on-demand
            if sync_enabled and auto_sync:
                if async_enabled:
                    # Use job queue for async sync
                    self.syncronize(
                        cursor, uid, model, action, ids, context=context)
                else:
                    # Sync synchronously
                    self.syncronize_sync(
                        cursor, uid, model, action, ids, context=context)
        except Exception:
            logger = logging.getLogger('openerp.odoo.sync')
            logger.exception(
                "Error during common_sync_model_create_update for model {}".format(model))

    def _clean_context_update_data(self, cursor, uid, context={}):
        res = context.copy()
        res.pop('update_last_sync', False)
        res.pop('update_odoo_created_sync', False)
        res.pop('update_odoo_updated_sync', False)
        res.pop('odoo_last_update_result', False)
        res.pop('sync_state', False)
        res.pop('odoo_id', False)
        return res

    def get_model_vals_to_sync(self, cursor, uid, model, id, context={}):
        rp_obj = self.pool.get(model)

        result_data = {}

        has_mapping_fk = (
            hasattr(rp_obj, 'MAPPING_FK') and rp_obj.MAPPING_FK
            and isinstance(rp_obj.MAPPING_FK, dict)
        )
        keys_no_direct_read = (
            rp_obj.MAPPING_FK.keys() if has_mapping_fk
            else []
        )

        # Read fields that are not foreign keys or related fields
        keys_to_read = [
            key for key in rp_obj.MAPPING_FIELDS_TO_SYNC.keys()
            if key not in keys_no_direct_read
        ]
        # TODO: check in prod if record id is already created when async
        data = rp_obj.read(cursor, uid, id, keys_to_read)

        # Read related fields if any
        has_related_fields = hasattr(rp_obj, 'get_related_values')
        if has_related_fields:
            related_values = rp_obj.get_related_values(cursor, uid, id, context=context)
            result_data.update(related_values)

        # Read and sync foreign key fields
        if has_mapping_fk:
            keys_fk = [key for key in rp_obj.MAPPING_FIELDS_TO_SYNC.keys()
                       if key in rp_obj.MAPPING_FK.keys()]
            if keys_fk:
                context_copy = self._clean_context_update_data(cursor, uid, context)
                context_copy['from_fk_sync'] = True
            for fk_field in keys_fk:
                model_fk = rp_obj.MAPPING_FK[fk_field]
                id_fk = rp_obj.read(cursor, uid, id, [fk_field])[fk_field]
                if id_fk:
                    odoo_id, erp_id = self.syncronize_sync(
                        cursor, uid, model_fk, 'sync', id_fk[0], context_copy)
                    if not odoo_id:
                        raise ForeingKeyNotAvailable("{},{}".format(model_fk, id_fk[0]))
                    data[fk_field] = odoo_id
                else:
                    data[fk_field] = None

        # Map fields to sync
        for erp_key, odoo_key in rp_obj.MAPPING_FIELDS_TO_SYNC.items():
            if erp_key in data:
                result_data[odoo_key] = data[erp_key]

        # Add constant fields
        has_mapping_constants = (
            hasattr(rp_obj, 'MAPPING_CONSTANTS') and rp_obj.MAPPING_CONSTANTS
            and isinstance(rp_obj.MAPPING_CONSTANTS, dict)
        )
        if has_mapping_constants:
            result_data.update(rp_obj.MAPPING_CONSTANTS)

        # Check False string fields and convert to empty string
        for key, value in result_data.items():
            if not (value is False or value is None):
                continue
            # get field type
            field_obj = rp_obj._columns.get(key, False)
            if field_obj and field_obj._type == 'char':
                result_data[key] = ''

        return result_data

    def check_erp_record_exist(self, cursor, uid, model, openerp_id):
        rp_obj = self.pool.get(model)
        max_attemps = 5
        attemp_n = 0
        while attemp_n < max_attemps:
            exists_erp_record = rp_obj.read(cursor, uid, openerp_id, ['name'])
            if not exists_erp_record:
                print("ERP RECORD NOT FOUND:", model, openerp_id)
                attemp_n += 1
                sleep(5)
            else:
                break
        if attemp_n == max_attemps:
            print("MAX ATTEMPS REACHED. SKIPPING SYNC FOR RECORD:", model, openerp_id)
            raise ERPObjectNotExistsException("{},{}".format(model, openerp_id))
        return True

    def get_dict_to_patch(self, cursor, uid, erp_data, odoo_data):
        modified_fields = {}
        for key in odoo_data.keys():
            if key in erp_data:
                odoo_field_data = odoo_data[key]
                if isinstance(odoo_field_data, list):
                    odoo_field_data = odoo_field_data[0]
                if isinstance(odoo_field_data, dict):
                    odoo_field_data = odoo_field_data['id']
                erp_value = False if erp_data[key] is None else erp_data[key]
                if erp_value != odoo_field_data:
                    modified_fields[key] = erp_data[key]
        return modified_fields

    @job(queue='sync_odoo', timeout=3600)
    def syncronize(self, cursor, uid,
                   model, action, openerp_id, context={},
                   check=True, update_check=True):
        context['update_last_sync'] = True
        self.syncronize_sync(cursor, uid, model, action, openerp_id,
                             context=context, check=check, update_check=update_check)

    def syncronize_sync(self, cursor, uid, model,
                        action, openerp_id, context=None, check=True, update_check=True):
        """
        Synchronizes a record between ERP and Odoo.
        """
        if context is None:
            context = {}

        # Ensure openerp_id is an integer if passed as a list
        if isinstance(openerp_id, list):
            openerp_id = openerp_id[0]

        # Check if model is static
        if model in STATIC_MODELS or context.get('is_static', False):
            odoo_id = self.get_or_create_static_odoo_id(
                cursor, uid, model, openerp_id, context.get('odoo_id', False), context
            )
            return odoo_id, openerp_id

        # Early return if synchronization is disabled for this specific model
        # in this case auto_sync and async_enabled are not relevant.
        # We need this check for on-demand syncs.
        sync_enabled, auto_sync, async_enabled = (
            self.sync_model_enabled_amplified(cursor, uid, model))
        if not sync_enabled:
            return False, False

        logger = logging.getLogger('openerp.odoo.sync')
        logger.info("Odoo syncronize {} with id {}".format(model, openerp_id))

        erp_data = {}
        rp_obj = self.pool.get(model)
        odoo_id, erp_id, odoo_metadata = False, False, False

        # Initialize sync status tracking
        sync_vals = {}

        try:
            # Verify record existence in the local ERP database
            self.check_erp_record_exist(cursor, uid, model, openerp_id)

            # Data preparation logic based on the action type
            if action in ['create', 'sync', 'write']:
                erp_data = self.get_model_vals_to_sync(
                    cursor, uid, model, openerp_id, context=context)
            elif action in ['unlink']:
                # Log placeholder for future implementations (PATCH/DELETE)
                logger.info("Action {} not implemented yet for model {}".format(action, model))
                sync_vals.update({
                    'sync_state': 'error',
                    'odoo_last_update_result': 'Action not implemented'
                })
                # We continue to check existence even if the specific update action isn't ready

            # Check if the record already exists in Odoo
            endpoint_suffix = rp_obj.get_endpoint_suffix(cursor, uid, openerp_id, context=context)
            odoo_id, erp_id, odoo_metadata = self.exists_in_odoo(
                cursor, uid, model, endpoint_suffix, openerp_id, context=context)

            if odoo_id:
                if not erp_id:
                    # Case: Record exists in Odoo but the link (erp_id) is missing
                    if self.update_erp_id(cursor, uid, model, odoo_id, openerp_id, context=context):
                        erp_id = openerp_id
                        sync_vals.update({
                            'sync_state': 'synced',
                            'update_last_sync': True,
                        })
                    else:
                        sync_vals.update({
                            'sync_state': 'error',
                            'odoo_last_update_result': 'Failed to link ERP_ID in Odoo',
                            'update_last_sync': True,
                        })
                else:
                    # Case: Already linked.
                    if not context.get('from_fk_sync', False):
                        sync_vals.update({
                            'sync_state': 'synced',
                            'update_last_sync': True,
                        })

                if MAPPING_MODELS_PATCH.get(model, False):
                    erp_data.pop('pnt_erp_id', False)
                    odoo_metadata.pop('company_id', False)
                    odoo_metadata.pop('company_name', False)
                    dict_to_patch = self.get_dict_to_patch(cursor, uid, erp_data, odoo_metadata)
                    if dict_to_patch:
                        success, msg = self.update_odoo_record(
                            cursor, uid, model, odoo_id, erp_id, dict_to_patch, context)
                        if not success:
                            sync_vals.update({
                                'sync_state': 'error',
                                'odoo_last_update_result': msg,
                                'update_last_sync': True,
                            })
            else:
                # Case: Record does not exist in Odoo, proceed to create it
                odoo_id, msg = self.create_odoo_record(
                    cursor, uid, model, erp_data, context=context)
                if odoo_id:
                    erp_id = openerp_id
                    sync_vals.update({
                        'sync_state': 'synced',
                        'update_odoo_created_sync': True,
                    })
                else:
                    sync_vals.update({
                        'sync_state': 'error',
                        'odoo_last_update_result': msg,
                        'update_last_sync': True,
                    })

        except (
            CreationNotSupportedException, UpdateNotSupportedException, ForeingKeyNotAvailable
        ) as e:
            sync_vals.update({
                'sync_state': 'error',
                'odoo_last_update_result': str(e),
                'update_last_sync': True,
            })
        except Exception as e:
            # Catch unexpected errors (Connection, Timeouts, etc.)
            logger.exception("Unexpected error during synchronization of {}".format(model))
            sync_vals.update({
                'sync_state': 'error',
                'odoo_last_update_result': str(e),
                'update_last_sync': True,
            })
        finally:
            # Single point of persistence for the sync log
            # Merge operation results into the context for the final DB update
            final_context = context.copy()
            final_context.update(sync_vals)
            self.update_odoo_id(cursor, uid, model, openerp_id, odoo_id, context=final_context)

        return odoo_id, erp_id

    def get_or_create_static_odoo_id(
            self, cursor, uid, model, openerp_id, odoo_id=False, context={}):
        sync_ids = self.search(cursor, uid, [
            ('model.model', '=', model),
            ('res_id', '=', openerp_id),
        ])
        if sync_ids:
            # sync record exists and we check if we need to update odoo_id
            sync_id = sync_ids[0]
            current_odoo_id = self.read(cursor, uid, sync_id, ['odoo_id'])['odoo_id']
            if odoo_id and odoo_id != current_odoo_id:
                self.write(cursor, uid, sync_id, {
                    'odoo_id': odoo_id,
                    'sync_state': 'static',
                }, context=context)
                return odoo_id
            return current_odoo_id

        # No sync record exists → create only if we have odoo_id
        if not odoo_id:
            return False

        # we create the static sync record
        sync_id = self.create(cursor, uid, {
            'model': self.pool.get('ir.model').search(
                cursor, uid, [('model', '=', model)], limit=1)[0],
            'res_id': openerp_id,
            'odoo_id': odoo_id,
            'sync_state': 'static',
        }, context=context)
        return odoo_id

    def create_odoo_record(self, cursor, uid, model, data, context={}):
        odoo_url_api, odoo_api_key = self._get_conn_params(cursor, uid)
        post_sufix = MAPPING_MODELS_POST.get(model, False)
        if post_sufix:
            url_base = '{}{}'.format(odoo_url_api, MAPPING_MODELS_POST.get(model))
            headers = {
                "X-API-Key": odoo_api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            response = requests.post(url_base, json=data, headers=headers)
            if response.status_code == 201:
                data = response.json()
                if data and 'success' in data and data.get('success', False):
                    odoo_id = data['data']['odoo_id']
                    return odoo_id, ''
            else:
                print("ERROR CREATING IN ODOO:", response.status_code, response.text)
                return False, response.text
        else:
            raise CreationNotSupportedException(model)
        return False, ''

    def update_odoo_record(self, cursor, uid, model, odoo_id, erp_id, data, context={}):
        # TODO: needs an endpoint with PATCH operation to implement this
        odoo_url_api, odoo_api_key = self._get_conn_params(cursor, uid)
        url_base = '{}{}/{}/{}'.format(
            odoo_url_api, MAPPING_MODELS_PATCH.get(model), odoo_id, erp_id)
        headers = {
            "X-API-Key": odoo_api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        response = requests.patch(url_base, json=data, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data and 'success' in data and data.get('success', False):
                return True, ''
        return False, response.text

    def exists_in_odoo(self, cursor, uid, model, url_sufix, erp_id, context={}):
        data = self.get_odoo_data(cursor, uid, model, url_sufix, context)
        if not data:
            return False, False, False
        if isinstance(data, list):
            if len(data) == 0:
                return False, False, False
            else:  # we filter by erp_id
                data = [d for d in data if d.get('erp_id', False) == erp_id]
                if len(data) == 0:
                    return False, False, False
                data = data[0]
        metadata = data.get('metadata', [{}])[0]
        return data.get('odoo_id', False), data.get('erp_id', False), metadata

    def get_odoo_data(self, cursor, uid, model, url_sufix, context={}):
        odoo_url_api, odoo_api_key = self._get_conn_params(cursor, uid)
        url_base = '{}{}/{}'.format(odoo_url_api, MAPPING_MODELS_GET.get(model), url_sufix)
        headers = {
            "X-API-Key": odoo_api_key,
            "Accept": "application/json",
        }
        response = requests.get(url_base, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data and 'success' in data and data.get('success', False):
                return data.get('data')
        return False

    def update_odoo_id(self, cursor, uid, model, openerp_id, odoo_id, context=None):
        if context is None:
            context = {}

        str_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        ids = self.search(cursor, uid, [
            ('model.model', '=', model),
            ('res_id', '=', openerp_id),
        ])

        if not ids:
            return self._create_sync_record(
                cursor, uid, model, openerp_id, odoo_id, str_now, context
            )
        else:
            vals, update = self._build_update_vals(
                cursor, uid, ids[0], odoo_id, str_now, context
            )
            if update:
                self.write(cursor, uid, ids, vals, context=context)

        return True

    def _create_sync_record(self, cursor, uid, model, openerp_id, odoo_id, str_now, context):
        model_id = self.pool.get('ir.model').search(
            cursor, uid, [('model', '=', model)], limit=1
        )[0]

        vals = {
            'model': model_id,
            'res_id': openerp_id,
            'odoo_id': odoo_id,
            'odoo_last_sync_at': str_now,
            'sync_state': 'synced',
        }

        if context.get('update_odoo_created_sync'):
            vals.update({
                'odoo_created_at': str_now,
            })

        if context.get('odoo_last_update_result'):
            vals.update({
                'odoo_last_update_result': context['odoo_last_update_result'],
                'sync_state': 'error',
            })

        return self.create(cursor, uid, vals)

    def _build_update_vals(self, cursor, uid, id, odoo_id, str_now, context):
        vals = {'odoo_id': odoo_id}
        update = False

        if context.get('update_last_sync'):
            vals.update({
                'odoo_last_sync_at': str_now,
                'sync_state': 'synced',
            })
            update = True

        if context.get('update_odoo_created_sync'):
            vals.update({
                'odoo_created_at': str_now,
                'sync_state': 'synced',
            })
            update = True

        if context.get('update_odoo_updated_sync'):
            vals.update({
                'odoo_updated_at': str_now,
                'sync_state': 'synced',
            })
            update = True

        if context.get('odoo_last_update_result'):
            vals['odoo_last_update_result'] = context['odoo_last_update_result']
            update = True

        if context.get('sync_state'):
            vals['sync_state'] = context['sync_state']
            update = True

        # Special case: error → synced
        sync_record = self.browse(cursor, uid, id)
        if sync_record.sync_state == 'error' and vals.get('sync_state') == 'synced':
            vals.update({
                'odoo_last_sync_at': str_now,
                'odoo_last_update_result': '',
            })
            update = True

        # Case Odoo_id change
        if sync_record.odoo_id != odoo_id:
            vals.update({
                'odoo_last_sync_at': str_now,
                'sync_state': 'synced',
            })
            update = True

        return vals, update

    def update_erp_id(self, cursor, uid, model, odoo_id, erp_id, context={}):
        odoo_url_api, odoo_api_key = self._get_conn_params(cursor, uid)
        url_base = "{}entity/{}/{}/{}".format(
            odoo_url_api, MAPPING_MODELS_ENTITIES.get(model), odoo_id, erp_id
        )
        headers = {
            "X-API-Key": odoo_api_key,
            "Accept": "application/json",
        }
        response = requests.patch(url_base, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data and 'success' in data and data.get('success', False):
                return True
        print("ERROR UPDATING ERP_ID IN ODOO:", response.status_code, response.text)
        return False

    def get_erp_data(self, cursor, uid, model, erp_id, context={}):
        rp_obj = self.pool.get(model)
        fields = list(rp_obj.MAPPING_FIELDS_TO_SYNC.keys())
        data = rp_obj.read(cursor, uid, erp_id, fields)
        return data

    def check_update_odoo_data(self, cursor, uid, model, odoo_id, erp_id, context={}):
        rp_obj = self.pool.get(model)
        # get odoo data
        url_sufix = rp_obj.get_endpoint_suffix(
            cursor, uid, erp_id, context=context
        )
        odoo_data = self.get_odoo_data(cursor, uid, model, url_sufix, context={})
        odoo_data.pop('odoo_id', None)
        odoo_data.pop('erp_id', None)

        # get erp data
        erp_data = self.get_model_vals_to_sync(
            cursor, uid, model, erp_id, context=context)

        # compare data and if diffent update Odoo
        if odoo_data != erp_data:
            return (model, odoo_id, erp_data)

        return (False, False, False)

    def _get_erp_name(self, cursor, uid, ids, name, args, context=None):
        if context is None:
            context = {}

        result = {}
        for sync in self.browse(cursor, uid, ids, context=context):
            erp_name = False

            if sync.model and sync.res_id:
                try:
                    model_name = sync.model.model
                    rp_obj = self.pool.get(model_name)
                    if rp_obj:
                        rec = rp_obj.read(
                            cursor, uid, sync.res_id, ['name'], context=context
                        )
                        erp_name = rec and rec.get('name') or False
                except Exception:
                    # Registro borrado, modelo no cargado, etc.
                    erp_name = False

            result[sync.id] = erp_name

        return result

    _columns = {
        'model': fields.many2one('ir.model', 'Model'),
        'res_id': fields.integer('ERP id'),
        'odoo_id': fields.integer('Odoo id'),
        # Aquest camp indica la última vegada que hem fet sync amb Odoo (s'hagin modificat o no les dades)  # noqa: E501
        'odoo_last_sync_at': fields.datetime('Odoo last sync at'),
        # Aquests camps indiquen la data de creacio i ultima modificacio al Odoo, no la data d'actualitzció de l'odoo_id a OpenERP  # noqa: E501
        'odoo_created_at': fields.datetime('Odoo created at'),
        'odoo_updated_at': fields.datetime('Odoo updated at'),
        # Resultat de l'error de la última actualització
        'odoo_last_update_result': fields.text('Odoo last update error'),
        'sync_state': fields.selection([
            ('synced', 'Synced'),
            ('pending', 'Pending'),
            ('error', 'Error'),
            ('static', 'Static'),
        ], 'Syncronization state', required=True),
        'erp_name': fields.function(
            _get_erp_name,
            type='char',
            size=256,
            string='ERP Name',
            method=True,
            store=False,
        ),
    }

    _sql_constraints = [
        ('model_res_id_uniq', 'unique (model,res_id)', ("Model and res_id must be unique"))
    ]

    _defaults = {
        'sync_state': lambda obj, cr, uid, context: 'pending',
    }


OdooSync()
