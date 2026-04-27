"""
Optional: FastAPI webhook receiver for Web3Forms submissions.

This is OPTIONAL and not required. The app works fine with manual email copy/paste.

To enable:
1. pip install fastapi uvicorn
2. Run: uvicorn webhook_receiver:app --reload --port 8000
3. Use ngrok to expose: ngrok http 8000
4. Add ngrok URL to Web3Forms "Redirect" field
5. Web3Forms will POST submissions directly to /webhook/web3forms

To use without webhooks:
- Skip this file entirely
- Use "Import Leads" > "Web3Forms Email Paste" instead
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import database
import lead_scoring
from datetime import datetime

app = FastAPI()

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "AqueLyst Hunter Webhook Receiver is running"}

@app.post("/webhook/web3forms")
async def handle_web3forms(request: Request):
    """
    Handle Web3Forms POST submission.

    Web3Forms sends form data as multipart/form-data or JSON.
    Extract lead information and add to database.
    """
    try:
        # Get form data
        form_data = await request.form()

        # Extract fields
        lead_data = {
            'business_name': form_data.get('business_name', form_data.get('name', 'Unknown')),
            'contact_name': form_data.get('name'),
            'email': form_data.get('email'),
            'phone': form_data.get('phone'),
            'website': form_data.get('website'),
            'city': form_data.get('city'),
            'state': form_data.get('state'),
            'business_type': form_data.get('business_type'),
            'message': form_data.get('message'),
            'pain_hypothesis': form_data.get('main_problem'),
            'product_fit': form_data.get('product_interest'),
            'lead_source': 'web3forms_webhook',
            'source_channel': 'website_form'
        }

        # Validate required fields
        if not lead_data['email'] or not lead_data['business_name']:
            return JSONResponse(
                status_code=400,
                content={"error": "Missing required fields: email, business_name"}
            )

        # Add lead to database
        lead_id = database.add_lead(**lead_data)

        if not lead_id:
            return JSONResponse(
                status_code=400,
                content={"error": "Lead with this email already exists"}
            )

        # Calculate score
        score = lead_scoring.calculate_lead_score(lead_data)
        product_fit, fit_score = lead_scoring.match_product(lead_data)

        # Update with score
        database.update_lead(
            lead_id,
            lead_score=score,
            product_fit=product_fit,
            status='new'
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "lead_id": lead_id,
                "score": score,
                "message": f"Lead captured: {lead_data['business_name']}"
            }
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@app.post("/webhook/test")
async def test_webhook():
    """Test endpoint for webhook verification."""
    return {"status": "Webhook is working"}

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting AqueLyst Hunter Webhook Receiver...")
    print("📡 Listening on http://localhost:8000")
    print("🔗 Use ngrok to expose: ngrok http 8000")
    print("✅ Add ngrok URL to Web3Forms redirect field")
    uvicorn.run(app, host="0.0.0.0", port=8000)
