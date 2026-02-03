{
    "name": "Syncronize OpenERP with Odoo",
    "description": """Som Sync""",
    "version": "0.1",
    "author": "Som Energia SCCL",
    "website": "https://github.com/Som-Energia/som_sync_openerp_modules",
    "category": "Added functionality",
    "depends": [
        'account',
        'account_payment_extension',
        'base_extended_som',
        'base_iban',
        'l10n_ES_partner',
        'partner_address_tipovia',
    ],
    "demo_xml": [
        "demo/odoo_sync_demo.xml",
    ],
    "init_xml": [],
    "update_xml": [
        "data/som_sync_openerp_data.xml",
        "views/odoo_sync_view.xml",
        "wizard/wizard_sync_object_odoo_view.xml",
        "wizard/wizard_open_related_model_record_view.xml",
        "security/ir.model.access.csv",
    ],
    "installable": True,
    "active": False,
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
