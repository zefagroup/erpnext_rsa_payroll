from __future__ import unicode_literals
from frappe import _

def get_data():
	return [
		{
			"label": _("Setup"),
			"icon": "fa fa-cog",
			"items": [
                {
                    "type": "doctype",
                    "name": "PAYE Tax Years",
                    "description": _("Pay As You Earn Tax Years"),
                },
                {
                    "type": "doctype",
                    "name": "PAYE Employee Tax",
                    "description": _("Pay As You Earn employee tax tables"),
                },
                {
                    "type": "doctype",
                    "name": "TC Primary Industry",
                    "description": _("VAT 403 Trade Classifications"),
                },
			]
		},
        {
            "label": _("Payroll"),
            "items": [
                {
                    "type": "doctype",
                    "name": "Employee Tax Directives",
                    "description": _("Employee Tax Directives"),
                },
            ]
        },
	]