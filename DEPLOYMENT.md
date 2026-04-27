# AqueLyst Hunter - Deployment & Operations Guide

**For: AqueLyst Team**  
**Date: April 25, 2026**  
**Status: Ready for Production**

---

## 🎯 What This System Does

**AqueLyst Hunter** is your local sales management platform for Duo Equine. It captures website leads, scores them, generates personalized outreach, and tracks follow-ups—all without cloud hosting or paid APIs.

### The Flow
```
Website Visitor → Web Form → Email → Copy to App → Auto-scored → 
Personalized Message → Human Approval → Send → Track Follow-up → Close Sale
```

---

## 🚀 Getting Started (Right Now)

### **Fastest Way to Start (macOS)**

```bash
# 1. Double-click launch.sh in Finder
# OR run in Terminal:
cd /Users/debraleblang/Desktop/AqueLyst-Hunter
./launch.sh
```

**Dashboard opens at `http://localhost:8501`**

### **If You Prefer Terminal**

```bash
cd /Users/debraleblang/Desktop/AqueLyst-Hunter
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt
python3 run_app.py
```

### **Load Sample Data**
1. Open dashboard (http://localhost:8501)
2. Click **⚙️ Settings** (bottom of sidebar)
3. Click **"Seed Database with Sample Data"**
4. 10 sample leads are loaded instantly

---

## 📋 First-Time Setup Checklist

### **1. Create Web3Forms Account (10 min)**
- Go to https://web3forms.com
- Sign up (free)
- Copy your **Access Key**

### **2. Update HTML Form Template**
- Open `web3forms_template.html`
- Find: `value="YOUR_ACCESS_KEY_HERE"`
- Replace with your actual Access Key
- Save

### **3. Add Form to Website (5-10 min)**
**Option A: Copy HTML directly**
- Open `web3forms_template.html` in text editor
- Copy entire HTML
- Paste into AqueLyst.com contact page

**Option B: Webflow/Wix/Page Builder**
- Copy HTML form code
- Create custom code section
- Paste form

**Option C: Link to File**
- Host the `web3forms_template.html` file on your web server
- Link to it or iframe it

### **4. Test the Form (2 min)**
- Fill out the form on your website
- Check your email (Web3Forms sends it there)
- Copy the entire email body

### **5. Test App Import (1 min)**
- Go to **📥 Import Leads**
- Go to **"2️⃣ Web3Forms Email Paste"**
- Paste the email
- Click **"Parse & Import"**
- Lead appears in your database!

---

## 🎯 Daily Operations

### **Morning Routine (5 min)**
1. Open dashboard: `http://localhost:8501`
2. Check 🔥 **Hot Leads** (score ≥70)
3. Check **Follow-ups Due Today**
4. Click a hot lead → go to **📧 Outreach**

### **Generate & Send Outreach (per lead)**
1. **Outreach** tab
2. Enter **Lead ID**
3. Choose **Message Type** (cold email usually)
4. Click **Generate Message**
5. Read and edit message
6. Click **Approve & Save**
7. Later: Go to **📤 Export Data** → **Approved Emails**
8. Copy email text
9. Paste into Gmail
10. Send (with your email, not automated)

### **Update Lead Status**
1. **👥 Lead Database**
2. Find lead by ID or search
3. Click ID to view details
4. Change **Status** (contacted, interested, etc.)
5. Update **Notes**
6. Click **"Update Lead #ID"**

### **Track Follow-ups**
1. In Lead Details view
2. See **Next Follow-up Date**
3. Come back on that date
4. Update status → "follow_up_due"
5. Generate new message
6. Approve and send

---

## 📊 Weekly Reports

### **Get Hot Leads Only**
1. **📤 Export Data**
2. Click **"Export Hot Leads"**
3. Download CSV
4. Use for priority calling/outreach

### **Get People to Call**
1. **📤 Export Data**
2. Click **"Export Call List"**
3. Download CSV (names + phones)
4. Print or open in phone app
5. Dial through the list

### **Get Conversion Metrics**
1. **📊 Dashboard**
2. See:
   - Total leads
   - Hot leads
   - Interested
   - Closed won
   - Conversion rate %
3. Take screenshot for reporting

---

## 🔐 Backup & Safety

### **Daily Backup (1 second)**
```bash
cp aquelyst_hunter.db aquelyst_hunter.db.backup
```

### **Weekly Export**
1. **📤 Export Data**
2. Click **"Export All Leads to CSV"**
3. Save CSV to safe location
4. You now have a backup outside the database

### **If Something Goes Wrong**
```bash
# Restore from backup
cp aquelyst_hunter.db.backup aquelyst_hunter.db

# Then restart app
python3 run_app.py
```

### **If Database Corrupts**
- Delete `aquelyst_hunter.db`
- Restart app (creates fresh database)
- Re-import from CSV backup

---

## 💡 Tips for Success

### **Lead Scoring Tips**
- Barns with 10+ stalls = higher score
- "Ammonia" or "flies" mentioned = higher score
- No email = lower score (can't contact)
- Contact name + phone + email = highest score

### **Message Generation Tips**
- Start with **cold_email** template
- Customize with specific details
- Mention their **problem** in message
- Always include **7-day trial** offer
- End with clear **call-to-action**

### **Follow-up Strategy**
- **Day 0**: Send cold email
- **Day 3**: Education email (how it works)
- **Day 7**: Trial offer (more formal)
- **Day 14**: Social proof (case study)
- **Day 21**: Seasonal reminder
- **Day 35**: Final check-in

### **Approval Workflow**
✅ Generate message  
✅ Read carefully  
✅ Check for typos  
✅ Verify customization  
✅ Approve  
✅ Later: copy to Gmail  
✅ Send (with your email)  

**All messages are drafts first. You approve before sending. No auto-spam.**

---

## 🤖 Optional: Ollama AI Setup

### **If You Want AI-Generated Messages**

```bash
# Install Ollama (macOS)
brew install ollama

# Start it (runs in background)
ollama serve

# Download a model (in new terminal)
ollama pull mistral
```

### **In the App**
- Go to **📧 Outreach**
- Check **"Use AI (Ollama)"**
- Select **"mistral"**
- Click **"Generate Message"**
- AI creates personalized message
- Edit and approve

### **Without Ollama**
- App uses professional templates
- Still works great
- No AI setup needed
- Fully functional system

---

## 🚨 Common Questions

### **Q: What if I don't use Web3Forms?**
A: You can import leads manually:
- CSV upload (bulk import)
- Manual entry (one at a time)
- Copy/paste Web3Forms email (without webhook)

### **Q: Can I use Gmail to send emails?**
A: Yes! 
1. Approve messages in app
2. Export approved emails
3. Copy text to Gmail
4. Send from your Gmail account
5. App doesn't auto-send (human approval required)

### **Q: What if Ollama isn't installed?**
A: App uses templates instead. No problem. Templates are professional and customizable.

### **Q: Can I customize the templates?**
A: Yes! Edit `outreach.py` and add your own templates or modify existing ones.

### **Q: How do I add new database fields?**
A: Edit `database.py`:
1. Add field to CREATE TABLE statement
2. Update add_lead() function
3. Update import_export.py if needed
4. Delete old database to create fresh schema

### **Q: Can I integrate with my CRM?**
A: Export to CSV and import into your CRM. Or modify `import_export.py` to add CRM integration.

### **Q: How many leads can it handle?**
A: Easily handles 1,000+ leads. SQLite is lightweight and fast.

### **Q: Is my data secure?**
A: Yes. Everything stays on your computer. No cloud. No external servers. You control it.

---

## 📈 Scaling Over Time

### **Month 1: Setup & Testing**
- Install and learn the system
- Test with sample data
- Get Web3Forms working
- Send first 10 outreaches
- Adjust messaging based on feedback

### **Month 2: Lead Generation**
- Website form capturing leads
- Daily database checks
- Generate 20-30 outreach messages
- Start seeing responses
- Track conversions

### **Month 3: Pipeline Development**
- 50+ leads in database
- Regular follow-up cadence
- First trials offered
- Conversion data shows what works
- Optimize messages based on data

### **Month 4+: Sales Machine**
- 100+ leads
- Predictable pipeline
- Regular closed sales
- Optimize lead scoring
- Maybe add team members (if needed)

---

## 🔧 Customization Guide

### **Change Scoring Logic**
File: `lead_scoring.py`
- Adjust point values for business types
- Add new problem keywords
- Change score thresholds

### **Edit Message Templates**
File: `outreach.py`
- Edit existing templates in `EMAIL_TEMPLATES` dict
- Add new message types
- Adjust tone and messaging

### **Add Database Fields**
Files: `database.py`, `app.py`, `import_export.py`
1. Add field to CREATE TABLE
2. Add to add_lead() parameters
3. Update update_lead() allowed_fields
4. Add to UI forms in app.py

### **Change Dashboard Layout**
File: `app.py`
- Modify `show_dashboard()` function
- Rearrange KPI cards
- Add new charts
- Change colors/styling

---

## 📞 Support & Troubleshooting

### **Dashboard won't load**
```bash
# Kill the old process
Ctrl+C

# Restart
python3 run_app.py
```

### **"Port 8501 already in use"**
```bash
# Use different port
streamlit run app.py --server.port 8502
```

### **Can't import CSV**
- Verify columns: `business_name` and `email` (required)
- Check file is CSV not XLSX
- Make sure emails don't have duplicates

### **Web3Forms not receiving submissions**
- Verify Access Key is correct in HTML
- Check spam folder
- Test directly on web3forms.com

### **Database locked error**
- Close the app
- Delete lock file (if exists): `rm aquelyst_hunter.db-wal`
- Restart app

---

## 🎯 Success Metrics

Track these to measure if system is working:

- **Leads captured**: Should increase weekly
- **Hot leads**: Should be 20-30% of total
- **Messages sent**: Should be 80%+ approved before sending
- **Follow-ups completed**: Should track next follow-up dates
- **Conversion rate**: Should improve as you refine messaging
- **Trial offers**: Should be tracking samples sent
- **Closed won**: The ultimate metric

---

## 📅 Maintenance Schedule

### **Daily**
- Check hot leads
- Send outreach
- Update lead status

### **Weekly**
- Backup database
- Review conversion metrics
- Generate reports
- Adjust messaging if needed

### **Monthly**
- Export full database
- Analyze what's working
- Update templates based on results
- Plan next month's strategy

### **Quarterly**
- Review all 90+ days old leads (follow up or close)
- Analyze top-performing messages
- Refine lead scoring weights
- Plan next quarter

---

## 🚀 You're Ready!

Everything is installed, tested, and ready to use. Your first sales are waiting.

### **Start Now:**
```bash
python3 run_app.py
```

### **Go to Dashboard:**
```
http://localhost:8501
```

### **Load Sample Data:**
Settings → Seed Database with Sample Data

### **Test with Real Leads:**
Import Leads → CSV or Web3Forms Email

### **Generate Your First Message:**
Outreach → Select Lead → Generate → Approve

### **Send It:**
Export → Copy to Gmail → Send

---

## 📧 Questions?

Refer to:
- **README.md** — Complete reference
- **QUICKSTART.md** — 5-minute setup
- **BUILD_SUMMARY.md** — Technical details
- Code comments in each Python file

---

**AqueLyst Hunter is your sales weapon. Use it daily and watch your pipeline grow.**

💪 Let's close some sales!

🎯
