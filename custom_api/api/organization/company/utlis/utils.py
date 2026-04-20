from custom_api.api.organization.company.utlis.terms_utils import get_company_terms
import frappe
from custom_api.api.organization.company.utlis.address_utils import create_or_update_company_address, get_company_addresses

def build_company_response(company):
    addresses = get_company_addresses(company.name)
    terms =  get_company_terms(company)
    return {
        "tpin": company.tax_id,
        "companyName": company.company_name,
        "industryType": company.domain,
        "dateOfIncorporation": company.date_of_incorporation,
        "companyType": company.custom_type,
        "registrationNumber": company.registration_details,
        "baseCurrency":company.default_currency,
        "contactInfo": {
            "companyEmail": company.email,
            "companyPhone": company.phone_no,
            "website": company.website,
        },

        "documents": {
            "companyLogoUrl": company.company_logo or "",
            "authorizedSignatureUrl": company.custom_company_signature or ""
        },
        "address": addresses[0] if addresses else None, # Assuming one address per company for now, can be extended to support multiple addresses in the future
        "terms": terms,
        "accountingSetup": {
                "chartOfAccounts": company.chart_of_accounts or "",
                "defaultExpenseGL": company.default_expense_account or "",
                "fxGainLossAccount": company.exchange_gain_loss_account or "",
                "roundOffAccount": company.round_off_account or "",
                "roundOffCostCenter": company.round_off_cost_center or "",
                "accumulatedDepreciationAccount": company.accumulated_depreciation_account or "",
                "depreciationExpenseAccount": company.depreciation_expense_account,
                "revaluationFrequency"          : company.auto_err_frequency or "", 
                "autoExchangeRateRevaluation"   : company.auto_exchange_rate_revaluation or 0,
                "unrealizedExchangeGainLossAccount": company.unrealized_exchange_gain_loss_account or "",
            },
    }

def map_company_update_fields(company, data):
    contact_info = data.get("contactInfo", {})
    company.company_name = data.get("companyName", company.company_name)
    company.tax_id = data.get("tpin", company.tax_id)

    # Contact Info
    company.email = contact_info.get("companyEmail", company.email)
    company.phone_no = contact_info.get("companyPhone", company.phone_no)
    company.website = contact_info.get("website", company.website)
    company.domain = data.get("industryType", company.domain)
    company.custom_type = data.get("companyType", company.custom_type)
    company.date_of_incorporation = data.get("dateOfIncorporation", company.date_of_incorporation)
    company.registration_details = data.get("registrationNumber", company.registration_details)
    create_or_update_company_address( company, data.get("address") )