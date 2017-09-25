# -*- coding: utf-8 -*-
# Copyright (c) 2017, Zefa Consulting and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.model.naming import make_autoname

class EmployeeTaxDirectives(Document):
	def autoname(self):
		self.name = make_autoname(self.employee + '/' + self.tax_year + '/' + self.directive_number + '/.###')

