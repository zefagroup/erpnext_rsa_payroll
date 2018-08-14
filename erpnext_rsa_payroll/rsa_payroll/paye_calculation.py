from __future__ import unicode_literals
import frappe, erpnext

from frappe.utils import add_days, cint, cstr, flt, getdate, rounded, date_diff, money_in_words
from frappe.model.naming import make_autoname

from frappe import msgprint, _
from erpnext.hr.doctype.payroll_entry.payroll_entry import get_start_end_dates
from erpnext.hr.doctype.employee.employee import get_holiday_list_for_employee
from erpnext.utilities.transaction_base import TransactionBase

def calculate_paye(doc, method):
	doc.set(doc.paye, 0.00)
	annual_gross = doc.gross_pay * 12
	age = pull_emp_details(doc)
	tax_year = get_tax_year(doc)
	tax_type = get_tax_type(doc)
	if tax_type.tax_type != 'Tax Directive':
		tax_table = get_tax_rate(tax_year.name, annual_gross, tax_type.tax_type)
		tax_rebate = get_tax_rebate(age, tax_table.parent)
		tax_threshold = get_tax_threshold(age, tax_table.parent)
		sum_taxable_earnings(doc, 'earnings', 'taxable_earnings', tax_table.parent)
		sum_taxable_deductions(doc, 'deductions', 'taxable_earnings', tax_table.parent)
		sum_uif(doc, tax_table.parent, 'uif')
		if doc.taxable_earnings >= tax_threshold:
			sum_paye(doc, tax_table, tax_rebate, 'paye', tax_type.tax_type)
	else:
		tax_directive = get_directive(doc)
		sum_taxable_earnings_directives(doc, 'taxable_earnings')
		sum_paye_directive(doc, tax_directive, 'paye')

	modify_bank_account(doc, 'modified_bank_account')

def get_tax_year(doc):
	tax_year = frappe.db.sql("select * from `tabPAYE Tax Years` where start_date <= %(start_date)s AND end_date >= %(end_date)s" ,
		{'start_date': doc.start_date, 'end_date': doc.end_date}, as_dict=1)
	return tax_year[0]

def get_tax_type(doc):
	tax_type = frappe.db.sql(""" select * from `tabSalary Structure` where name = %s""", (doc.salary_structure), as_dict=1)
	return tax_type[0]

def get_tax_rate(tax_year, annual_gross, tax_type):
	tax_table = frappe.db.sql("""select parent, bracket_min, bracket_max, base_tax, tax_rate from `tabPAYE Tax Rates`
		where bracket_max < %s AND parent in (select name from `tabPAYE Employee Tax` where tax_year = %s AND tax_type = %s)""",
		(annual_gross, tax_year, tax_type), as_dict=1)
	if not tax_table:
		tax_table = frappe.db.sql("""select parent, bracket_min, bracket_max, base_tax, tax_rate from `tabPAYE Tax Rates`
	    		where bracket_min = 0 AND parent in (select name from `tabPAYE Employee Tax` where tax_year = %s AND tax_type = %s)""",
								  (tax_year, tax_type), as_dict=1)
	return tax_table[0]
	
def pull_emp_details(doc):
	emp = frappe.db.get_value("Employee", doc.employee, ["date_of_birth"], as_dict=1)
	if emp:
		return date_diff(getdate(doc.end_date), getdate(emp.date_of_birth)) / 365
			
def get_tax_rebate(age, tax_table):
	if age < 65 :
		tax_rebate = frappe.db.sql(""" select name, rebate_amount from `tabPAYE Tax Rebates` where max_age = 64 AND parent in 
			(select name from `tabPAYE Employee Tax` where name = %s)""",
								   (tax_table), as_dict=1)
		return tax_rebate[0].rebate_amount
	elif age >= 65 and age < 75 :
		total_rebate = 0.00
		tax_rebate = frappe.db.sql(""" select name, rebate_amount from `tabPAYE Tax Rebates` where max_age < 75 AND parent in
			(select name from `tabPAYE Employee Tax` where name = %s)""", (tax_table), as_dict=1)
		for r in tax_rebate:
			total_rebate = total_rebate + r.rebate_amount
		return total_rebate
	elif age >= 75 :
		total_rebate = 0.00
		tax_rebate = frappe.db.sql(""" select name, rebate_amount from `tabPAYE Tax Rebates` where parent in 
		 	(select name from `tabPAYE Employee Tax` where name = %s)""", (tax_table), as_dict=1)

		for r in tax_rebate:
			total_rebate = total_rebate + r.rebate_amount
		return total_rebate

def get_tax_threshold(age, tax_table):
	if age < 65 :
		tax_threshold = frappe.db.sql(""" select name, threshold_amount from `tabPAYE Tax Threshold` where max_age = 64 AND parent in
		 	(select name from `tabPAYE Employee Tax` where name = %s)""", (tax_table), as_dict=1)
		return tax_threshold[0].threshold_amount
	elif age >= 65 and age < 75 :
		tax_threshold = frappe.db.sql(""" select name, threshold_amount from `tabPAYE Tax Threshold` where max_age < 75 AND parent in
			(select name from `tabPAYE Employee Tax` where name = %s)""", (tax_table), as_dict=1)
		return tax_threshold[0].threshold_amount
	elif age >= 75 :
		tax_threshold = frappe.db.sql(""" select name, threshold_amount from `tabPAYE Tax Threshold` where min_age = 75 AND parent in
			(select name from `tabPAYE Employee Tax` where name = %s)""", (tax_table), as_dict=1)
		return tax_threshold[0].threshold_amount

def sum_taxable_earnings(doc, component_type, total_field, tax_table):
	doc.set(total_field, 0.00)
	for d in doc.get(component_type):
		if d.taxable :
			deductable = frappe.db.sql(""" select taxable_portion, max_amount from `tabPAYE Deductables` where 
				salary_component = %(salary_component)s AND parent in (select name from `tabPAYE Employee Tax` where name = %(tax_table)s)""",
									   {'salary_component': d.salary_component, 'tax_table': tax_table}, as_dict=1)
			amount = 0.0
			if not deductable:
				if doc.payroll_frequency == 'Monthly':
					amount = d.amount * 12
				elif doc.payroll_frequency == 'Fortnightly':
					amount = d.amount * 12 * 2
				elif doc.payroll_frequency == 'Weekly':
					amount = d.amount * 12 * 4.34524
			else:
				if doc.payroll_frequency == 'Monthly':
					amount = flt(d.amount) * flt(deductable[0].taxable_portion) * 12
				elif doc.payroll_frequency == 'Fortnightly':
					amount = flt(d.amount) * flt(deductable[0].taxable_portion) * 12 * 2
				elif doc.payroll_frequency == 'Weekly':
					amount = flt(d.amount) * flt(deductable[0].taxable_portion) * 12 * 4.34524
			doc.set(total_field, doc.get(total_field) + flt(amount))

def sum_taxable_earnings_directives(doc, total_field):
	doc.set(total_field, 0.00)
	doc.set(total_field, doc.get(total_field) +(doc.gross_pay * 12))

def sum_taxable_deductions(doc, component_type, total_field, tax_table):
	for d in doc.get(component_type):
		if d.taxable :
			deductable = frappe.db.sql(""" select taxable_portion, max_amount from `tabPAYE Deductables` where 
				salary_component = %(salary_component)s AND parent in (select name from `tabPAYE Employee Tax` where name = %(tax_table)s)""",
									   {'salary_component': d.salary_component, 'tax_table': tax_table}, as_dict=1)

			amount = 0.0
			if deductable:
				if doc.payroll_frequency == 'Monthly':
					amount = flt(d.amount) * 12
				elif doc.payroll_frequency == 'Fortnightly':
					amount = flt(d.amount) * 12 * 2
				elif doc.payroll_frequency == 'Weekly':
					amount = flt(d.amount) * 12 * 4.34524

			doc.set(total_field, doc.get(total_field) - (flt(amount)))

def sum_paye(doc, tax_table, tax_rebate, total_field, tax_type):
	doc.set(total_field, 0.00)
	if tax_type == 'PAYE':
		raw_tax = (doc.taxable_earnings - tax_table.bracket_min) * tax_table.tax_rate
		paye_sum = tax_table.base_tax + (raw_tax - tax_rebate) / 12
	elif doc.tax_type == 'Non-Standard':
		raw_tax = doc.gross_pay * tax_table.tax_rate * 12
		paye_sum = (raw_tax - tax_rebate) / 12
	doc.set(total_field, paye_sum)

def sum_paye_directive(doc, tax_directive, total_field):
	doc.set(total_field, 0.00)
	print(doc.paye)
	if tax_directive.directive_type == 'Fixed Percentage':
		paye_sum = doc.gross_pay * tax_directive.tax_percentage
	else:
		paye_sum = tax_directive[0].tax_amount / 12
	doc.set(total_field, paye_sum)
	print(doc.paye)

def sum_uif(doc, tax_table, total_field):
	doc.set(total_field, 0.00)
	uif_ceiling = frappe.db.sql(""" select annual_ceiling, monthly_ceiling from `tabUIF Ceiling` where parent in 
		(select name from `tabPAYE Employee Tax` where name = %s)""", (tax_table), as_dict=1)
	if uif_ceiling:
		if doc.payroll_frequency == 'Monthly':
			ceiling = uif_ceiling[0].monthly_ceiling
		elif doc.payroll_frequency == 'Fortnightly':
			ceiling = (uif_ceiling[0].monthly_ceiling) / 2
		elif doc.payroll_frequency == 'Weekly':
			ceiling = (uif_ceiling[0].monthly_ceiling) / 4.34524
	else:
		if doc.payroll_frequency == 'Monthly':
			ceiling = 148.72
		elif doc.payroll_frequency == 'Fortnightly':
			ceiling = 148.72 / 2
		elif doc.payroll_frequency == 'Weekly':
			ceiling = 148.72 / 4.34524

	uif = doc.gross_pay * 0.01
	if uif > ceiling:
		doc.set(total_field, ceiling)
	else:
		doc.set(total_field, uif)

def modify_bank_account(doc, set_field):
	if doc.bank_account_no:
		acc_no = doc.bank_account_no
		acc_len = len(acc_no[:-4])
		new_acc_part1 = "x" * acc_len
		new_acc = new_acc_part1 + acc_no[-4:]
		doc.set(set_field, new_acc)

def get_directive(doc):
	tax_year = get_tax_year(doc)
	tax_directive = frappe.db.sql(""" select directive_type, tax_amount, tax_percentage from `tabEmployee Tax Directives`
		where employee = %s AND tax_year = %s""", (doc.employee, tax_year.name), as_dict=1)
	if tax_directive:
		return tax_directive[0]