# AqueLyst Hunter - Quick Reference

## 🎯 Launch App
```bash
cd /Users/debraleblang/Desktop/AqueLyst-Hunter
./launch.sh
# OR: python3 run_app.py
```
**Dashboard:** `http://localhost:8501`

---

## 📋 Core Modules

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| **app.py** | Streamlit dashboard UI | show_dashboard(), show_lead_database(), show_outreach() |
| **database.py** | SQLite operations | add_lead(), get_lead(), update_lead(), get_dashboard_stats() |
| **lead_scoring.py** | Score leads 0-100 | calculate_lead_score(), match_product() |
| **outreach.py** | Message generation | generate_outreach(), check_ollama_available() |
| **import_export.py** | CSV & email parsing | import_csv(), parse_web3forms_submission(), export_csv() |
| **web3forms_template.html** | Website lead form | (standalone HTML - no code) |
| **webhook_receiver.py** | Optional webhook | FastAPI endpoint for direct Web3Forms integration |

---

## 🗄️ Database Schema

### `leads`
```sql
id, business_name, contact_name, email, phone
website, social_url
city, state, business_type
lead_source, source_channel
message, pain_hypothesis, product_fit
lead_score (0-100), status
last_contacted, next_follow_up_date
notes, opt_out
created_at, updated_at
```

### `outreach_drafts`
```sql
id, lead_id, message_type, subject, content
approved (0/1), sent (0/1), created_at
```

### `follow_ups`
```sql
id, lead_id, follow_up_type, scheduled_date
completed (0/1), created_at
```

---

## 🎯 Lead Statuses

```
new → researched → drafted → contacted → 
follow_up_due → interested → trial_offered → 
sample_sent → closed_won / closed_lost / opted_out
```

---

## 📊 Dashboard Tabs

| Tab | Purpose | Key Actions |
|-----|---------|-------------|
| **📊 Dashboard** | Overview & KPIs | View hot leads, due follow-ups, conversion rate |
| **👥 Lead Database** | Manage leads | View, edit, filter, delete leads |
| **📧 Outreach** | Generate messages | Create, edit, approve email drafts |
| **📥 Import Leads** | Add leads | CSV upload, Web3Forms email paste |
| **📤 Export Data** | Download reports | All leads, hot leads, call list, approved emails |
| **⚙️ Settings** | System config | Check status, load sample data |

---

## 📧 Message Types (10 Templates)

1. **cold_email** — Initial contact
2. **reply_to_inbound** — Response to inquiry
3. **instagram_dm** — Casual DM
4. **facebook_message** — Social message
5. **phone_opener** — Call script
6. **follow_up_education** — Explain how it works
7. **trial_offer** — 7-day barn trial
8. **social_proof** — Case study
9. **objection_budget** — Budget response
10. **objection_timing** — Timing response

---

## 🎯 Lead Scoring Weights

| Factor | Points | Details |
|--------|--------|---------|
| Business Type | 0-30 | Barn/stable/boarding = 30 pts |
| Problem Keywords | 0-25 | Ammonia/flies/odor = 8-10 pts each |
| Contact Completeness | 0-20 | Email = 7, phone = 7, website = 3 |
| Engagement Signals | 0-15 | Contact name = 5, website = 5 |
| Stall Count | 0-10 | 10+ stalls = bonus 10 pts |
| **Total** | **0-100** | Auto-calculated per lead |

---

## 📥 Import Methods

### CSV Format
```csv
business_name,contact_name,email,phone,city,state,business_type,pain_hypothesis
Smith Stable,John Smith,john@smith.com,555-0100,Austin,TX,stable,Ammonia odor
```

### Web3Forms Email Paste
1. Copy email from Web3Forms
2. Paste full email body in app
3. App extracts: name, email, phone, business, problem
4. Lead is auto-created

---

## 📤 Export Formats

- **All Leads** → Complete CSV dump
- **Hot Leads** → Score ≥70 only
- **Call List** → Name, phone, status
- **Approved Emails** → Ready-to-send messages

---

## 🌐 Web3Forms Setup

```html
<!-- In web3forms_template.html, replace: -->
<input type="hidden" name="access_key" value="YOUR_ACCESS_KEY_HERE">

<!-- With your actual key from web3forms.com -->
<input type="hidden" name="access_key" value="abc123xyz789...">
```

**Then:**
1. Copy HTML to website
2. Fill form
3. Check email
4. Paste in app
5. Lead imported

---

## 🤖 Ollama Setup (Optional)

```bash
# Install
brew install ollama

# Start (background)
ollama serve

# Get model
ollama pull mistral

# In app: Check "Use AI (Ollama)" → Generate
```

**Without Ollama:** App uses templates (works fine)

---

## 🔄 Daily Workflow

1. **Open app** → `python3 run_app.py`
2. **Check hot leads** → Dashboard
3. **Pick a lead** → Lead Database
4. **Generate message** → Outreach tab
5. **Customize** → Edit text
6. **Approve** → Save as draft
7. **Export** → Download approved emails
8. **Send** → Copy to Gmail (your email)
9. **Update status** → Lead Database
10. **Schedule follow-up** → Set next contact date

---

## 🚨 Common Commands

### Backup
```bash
cp aquelyst_hunter.db aquelyst_hunter.db.backup
```

### Restore
```bash
cp aquelyst_hunter.db.backup aquelyst_hunter.db
```

### Clear Database
```bash
rm aquelyst_hunter.db
# Restart app to create fresh database
```

### Use Different Port
```bash
streamlit run app.py --server.port 8502
```

---

## 📊 Key Metrics

Track in **Dashboard**:
- Total leads
- Hot leads (≥70 score)
- New leads (today)
- Follow-ups due
- Interested
- Trial offers
- Closed won
- Conversion rate %

---

## 🎯 Product Matching

Currently: **Duo Equine** (all leads)

**Triggers:**
- Ammonia problems
- Fly control issues
- Barn smell/odor
- Horse stalls
- Trailers
- Bedding
- Manure management
- Equine facility care

---

## 📚 Documentation Files

| File | Purpose |
|------|---------|
| **README.md** | Complete feature documentation |
| **QUICKSTART.md** | 5-minute setup guide |
| **BUILD_SUMMARY.md** | What was built + features |
| **DEPLOYMENT.md** | Operations & daily use guide |
| **REFERENCE.md** | This file - quick lookup |

---

## 🔧 Customization Cheat Sheet

### Add Template
Edit `outreach.py`:
```python
EMAIL_TEMPLATES = {
    "my_template": """Hi {contact_name},
Your custom message here...
{your_name}"""
}
```

### Change Scoring
Edit `lead_scoring.py`:
```python
target_business_types = {
    "barn": 30,  # change these numbers
    "stable": 30,
}
```

### Add Database Field
Edit `database.py`:
```sql
ALTER TABLE leads ADD COLUMN new_field TEXT;
```

### Modify Dashboard
Edit `app.py` → `show_dashboard()` function

---

## ✅ Checklist: Is System Ready?

- [x] All Python files created
- [x] Database initializes without error
- [x] Sample data loads successfully
- [x] Lead scoring works (0-100)
- [x] Message generation works (templates + AI optional)
- [x] CSV import/export works
- [x] Web form HTML is complete
- [x] Documentation is comprehensive
- [x] Dashboard is functional
- [x] All features tested

---

## 📞 Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| Dashboard won't load | Ctrl+C → python3 run_app.py |
| Port 8501 in use | streamlit run app.py --server.port 8502 |
| Can't import CSV | Check columns: business_name, email required |
| Message won't generate | Select a lead first, then message type |
| Web form not working | Check Access Key in HTML |
| Database corrupted | Delete aquelyst_hunter.db, restart |

---

## 🎯 Success Indicators

✅ **Week 1:** System running, sample data loaded  
✅ **Week 2:** Web3Forms working, first real leads imported  
✅ **Week 3:** Outreach messages generated and approved  
✅ **Week 4:** First responses received, status tracking working  
✅ **Month 2:** First trial offered, first sale closing  

---

## 🚀 Ready to Launch

**Everything is built, tested, and ready to use.**

```bash
python3 run_app.py
```

**Then:** Open `http://localhost:8501` in browser

**Then:** Load sample data from Settings

**Then:** Start capturing and closing sales!

---

*AqueLyst Hunter - Your local sales operating system*
