# -*- coding: utf-8 -*-
import logging
import csv
import pooler
from addons import get_module_resource


def check_record_exists(cursor, model_name, res_id, uid=1):
    """
    Check if a record exists in the given model with the specified res_id.

    :param cursor: database cursor
    :param model_name: OpenERP model name (e.g. 'payment.type')
    :param res_id: record id to check
    :param uid: user id (default: 1)
    :return: True if record exists, False otherwise
    """
    pool = pooler.get_pool(cursor.dbname)
    model_obj = pool.get(model_name)
    record_ids = model_obj.search(cursor, uid, [('id', '=', res_id)])
    return bool(record_ids)


def create_static_mappings_from_csv(
    cursor,
    model_name,
    csv_path,
    erp_id_field='erp_id',
    odoo_id_field='odoo_id',
    uid=1
):
    """
    Create or update static odoo.sync mappings from a CSV file.

    :param cursor: database cursor
    :param model_name: OpenERP model name (e.g. 'payment.type')
    :param csv_path: absolute path to CSV file
    :param erp_id_field: CSV column name for ERP id
    :param odoo_id_field: CSV column name for Odoo id
    :param uid: user id (default: 1)
    """
    logger = logging.getLogger('openerp.migration')
    pool = pooler.get_pool(cursor.dbname)

    sync_obj = pool.get('odoo.sync')
    model_obj = pool.get('ir.model')

    # Get ir.model id for the given model
    model_ids = model_obj.search(
        cursor, uid, [('model', '=', model_name)]
    )
    if not model_ids:
        logger.error("Model %s not found in ir.model", model_name)
        return

    model_id = model_ids[0]

    created_and_update_count = 0
    skipped_count = 0
    total_count = 0

    with open(csv_path, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            total_count += 1
            try:
                erp_id = int(row.get(erp_id_field, 0))
                odoo_id = int(row.get(odoo_id_field, 0))
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid ERP/Odoo id in row: %s", row
                )
                continue

            # Skip invalid ERP ids
            if erp_id <= 0 or odoo_id <= 0:
                logger.info(
                    "Skipping row with invalid ids (ERP: %s, Odoo: %s)",
                    erp_id, odoo_id
                )
                skipped_count += 1
                continue

            # Check if mapping already exists
            sync_ids = sync_obj.search(cursor, uid, [
                ('model', '=', model_id),
                ('res_id', '=', erp_id),
            ])

            if sync_ids:
                # Update existing mapping if needed
                sync_obj.write(cursor, uid, sync_ids, {
                    'odoo_id': odoo_id,
                    'sync_state': 'static',
                })
                created_and_update_count += 1
                logger.info(
                    "Updated static mapping %s ERP %s → Odoo %s",
                    model_name, erp_id, odoo_id
                )
            else:
                # Check if the record exists in the target model
                if not check_record_exists(cursor, model_name, erp_id, uid):
                    logger.warning(
                        "Target record %s id %s does not exist. Skipping mapping.",
                        model_name, erp_id
                    )
                    skipped_count += 1
                    continue

                # Create new static mapping
                sync_obj.create(cursor, uid, {
                    'model': model_id,
                    'res_id': erp_id,
                    'odoo_id': odoo_id,
                    'sync_state': 'static',
                })
                logger.info(
                    "Created static mapping %s ERP %s → Odoo %s",
                    model_name, erp_id, odoo_id
                )
                created_and_update_count += 1

    logger.info(
        "\nCompleted static mappings for model %s:\n"
        ">> Created/updated: %s created/updated.\n"
        ">> Skipped: %s invalid entries.\n"
        ">> Total processed: %s entries.\n",
        model_name, created_and_update_count, skipped_count, total_count
    )


def migrate(cursor, installed_version):
    if not installed_version:
        return

    logger = logging.getLogger('openerp.migration')
    logger.info("Creating static odoo.sync mappings")

    migrations = [
        {
            'model': 'res.country',
            'csv': 'res_country.csv',
        },
        {
            'model': 'payment.type',
            'csv': 'payment_type.csv',
        },
        {
            'model': 'account.fiscal.position',
            'csv': 'account_fiscal_position.csv',
        },
        {
            'model': 'account.payment.term',
            'csv': 'payment_term.csv',
        },
    ]

    for item in migrations:
        model_name = item['model']
        csv_file = item['csv']

        logger.info("Creating static %s mappings", model_name)

        csv_path = get_module_resource(
            'som_sync_openerp',
            'migrations',
            csv_file
        )

        if not csv_path:
            logger.warning("CSV not found for model %s, skipping", model_name)
            continue

        create_static_mappings_from_csv(
            cursor=cursor,
            model_name=model_name,
            csv_path=csv_path,
            erp_id_field='erp_id',
            odoo_id_field='odoo_id',
        )

        logger.info(
            "Static %s mappings creation completed successfully.",
            model_name
        )

    logger.info("Static odoo.sync mappings creation finished.")
