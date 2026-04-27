"""Import/export functionality for AqueLyst Hunter."""

import csv
import json
import re
from datetime import datetime
import pandas as pd
from database import add_lead, get_all_leads

def import_csv(filepath):
    """Import leads from CSV file."""
    imported = 0
    errors = []

    required_columns = {'business_name', 'email'}

    try:
        df = pd.read_csv(filepath)

        # Check for required columns
        if not required_columns.issubset(set(df.columns)):
            return 0, [f"CSV must contain at least: {', '.join(required_columns)}"]

        for idx, row in df.iterrows():
            try:
                lead_id = add_lead(
                    business_name=row.get('business_name', ''),
                    contact_name=row.get('contact_name'),
                    email=row.get('email'),
                    phone=row.get('phone'),
                    website=row.get('website'),
                    social_url=row.get('social_url'),
                    city=row.get('city'),
                    state=row.get('state'),
                    business_type=row.get('business_type'),
                    lead_source=row.get('lead_source', 'csv_import'),
                    source_channel=row.get('source_channel'),
                    message=row.get('message'),
                    pain_hypothesis=row.get('pain_hypothesis'),
                    product_fit=row.get('product_fit'),
                    notes=row.get('notes')
                )

                if lead_id:
                    imported += 1
                else:
                    errors.append(f"Row {idx+2}: Duplicate email or error adding lead")

            except Exception as e:
                errors.append(f"Row {idx+2}: {str(e)}")

    except Exception as e:
        return 0, [f"Error reading CSV: {str(e)}"]

    return imported, errors


def export_csv(filepath, filters=None):
    """Export leads to CSV."""
    leads = get_all_leads()

    if not leads:
        return False, "No leads to export"

    try:
        df = pd.DataFrame([dict(lead) for lead in leads])

        # Reorder columns for readability
        column_order = [
            'id', 'business_name', 'contact_name', 'email', 'phone',
            'website', 'city', 'state', 'business_type',
            'lead_source', 'message', 'pain_hypothesis', 'product_fit',
            'lead_score', 'status', 'next_follow_up_date', 'notes',
            'opt_out', 'created_at'
        ]

        # Ensure all columns exist
        for col in column_order:
            if col not in df.columns:
                df[col] = ''

        df = df[column_order]

        df.to_csv(filepath, index=False)
        return True, f"Exported {len(leads)} leads to {filepath}"

    except Exception as e:
        return False, f"Error exporting CSV: {str(e)}"


def parse_web3forms_submission(email_body):
    """
    Parse Web3Forms email submission.
    Extract fields from email body.
    """
    extracted = {
        'name': '',
        'email': '',
        'phone': '',
        'business_name': '',
        'city': '',
        'state': '',
        'problem': '',
        'message': '',
        'product_interest': '',
    }

    # Common field patterns from Web3Forms emails
    patterns = {
        'name': r'(?:Name|Full Name|Contact Name)[:\s]+([^\n]+)',
        'email': r'(?:Email|Email Address)[:\s]+([^\n@]+@[^\n]+)',
        'phone': r'(?:Phone|Phone Number)[:\s]+([^\n\d\-\(\)]*[\d\-\(\)]{6,}[^\n]*)',
        'business_name': r'(?:Business|Business Name|Company)[:\s]+([^\n]+)',
        'city': r'(?:City)[:\s]+([^\n]+)',
        'state': r'(?:State)[:\s]+([^\n]+)',
        'problem': r'(?:Problem|Main Problem|Main Issue|Pain Point)[:\s]+([^\n]+)',
        'message': r'(?:Message|Comments?|Details?|Notes?)[:\s]+([^\n]+)',
        'product_interest': r'(?:Product|Product Interest)[:\s]+([^\n]+)',
    }

    for field, pattern in patterns.items():
        match = re.search(pattern, email_body, re.IGNORECASE)
        if match:
            extracted[field] = match.group(1).strip()

    return extracted


def manual_import_web3forms(email_body):
    """
    Import a single lead from manually pasted Web3Forms email.
    """
    extracted = parse_web3forms_submission(email_body)

    if not extracted['email']:
        return None, "Could not extract email from submission"

    lead_id = add_lead(
        business_name=extracted['business_name'] or extracted['name'],
        contact_name=extracted['name'],
        email=extracted['email'],
        phone=extracted['phone'],
        city=extracted['city'],
        state=extracted['state'],
        message=extracted['message'],
        pain_hypothesis=extracted['problem'],
        product_fit=extracted['product_interest'],
        lead_source='web3forms',
        source_channel='website_form'
    )

    if lead_id:
        return lead_id, "Lead imported successfully"
    else:
        return None, "Duplicate email or error adding lead"


def export_approved_emails(filepath):
    """Export approved email drafts ready to send."""
    from database import get_approved_drafts, get_lead

    drafts = get_approved_drafts()

    if not drafts:
        return False, "No approved drafts to export"

    try:
        export_data = []

        for draft in drafts:
            lead = get_lead(draft['lead_id'])
            if lead:
                export_data.append({
                    'to_email': lead['email'],
                    'to_name': lead['contact_name'],
                    'subject': draft['subject'],
                    'message_type': draft['message_type'],
                    'body': draft['content'],
                    'draft_id': draft['id'],
                })

        df = pd.DataFrame(export_data)
        df.to_csv(filepath, index=False)
        return True, f"Exported {len(export_data)} approved emails to {filepath}"

    except Exception as e:
        return False, f"Error exporting emails: {str(e)}"


def export_call_list(filepath):
    """Export leads with phones for calling."""
    leads = get_all_leads()

    leads_with_phones = [
        l for l in leads
        if l['phone'] and l['status'] not in ['opted_out', 'closed_won', 'closed_lost']
    ]

    if not leads_with_phones:
        return False, "No leads with phone numbers"

    try:
        export_data = []
        for lead in leads_with_phones:
            export_data.append({
                'contact_name': lead['contact_name'],
                'phone': lead['phone'],
                'business_name': lead['business_name'],
                'status': lead['status'],
                'lead_score': lead['lead_score'],
                'problem': lead['pain_hypothesis'],
            })

        df = pd.DataFrame(export_data)
        df.to_csv(filepath, index=False)
        return True, f"Exported {len(export_data)} leads to call list"

    except Exception as e:
        return False, f"Error exporting call list: {str(e)}"


def export_hot_leads(filepath):
    """Export high-scoring leads."""
    from database import get_hot_leads

    leads = get_hot_leads()

    if not leads:
        return False, "No hot leads to export"

    try:
        df = pd.DataFrame([dict(lead) for lead in leads])
        df.to_csv(filepath, index=False)
        return True, f"Exported {len(leads)} hot leads to {filepath}"

    except Exception as e:
        return False, f"Error exporting hot leads: {str(e)}"
