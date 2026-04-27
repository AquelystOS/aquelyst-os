# AqueLyst Hunter - Quick Start Guide 🚀

**Get up and running in 5 minutes**

---

## Step 1: Install (2 min)

### macOS:
```bash
cd AqueLyst-Hunter
brew install python@3.11  # if needed
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Linux/Windows:
```bash
cd AqueLyst-Hunter
python3 -m venv venv
source venv/bin/activate  # or: venv\Scripts\activate (Windows)
pip install -r requirements.txt
```

---

## Step 2: Start the App (1 min)

### Option A: Easy (Recommended)
```bash
python3 run_app.py
```

### Option B: Direct
```bash
streamlit run app.py
```

**Dashboard opens at:** `http://localhost:8501`

---

## Step 3: Load Sample Data (1 min)

1. Open dashboard (localhost:8501)
2. Go to **⚙️ Settings** (bottom of left sidebar)
3. Click **"Seed Database with Sample Data"**
4. Go back to **📊 Dashboard**
5. You'll see 10 sample equine leads ready to use

---

## Step 4: Test the System (1 min)

### View Leads:
- Go to **👥 Lead Database**
- See 10 sample leads with scores
- Click a Lead ID to view details

### Generate Message:
- Go to **📧 Outreach**
- Enter **Lead ID: 1**
- Choose **Message Type: cold_email**
- Click **"Generate Message"**
- Edit and save as draft

### Export Leads:
- Go to **📤 Export Data**
- Click **"Export All Leads to CSV"**
- Opens file ready to use

---

## Step 5: Connect Web3Forms (Optional)

### A. Get Your Access Key:
1. Go to [web3forms.com](https://web3forms.com) (free account)
2. Grab your **Access Key** from dashboard

### B. Add to HTML Form:
1. Open `web3forms_template.html`
2. Find: `value="YOUR_ACCESS_KEY_HERE"`
3. Replace with your actual key
4. Save

### C. Put Form on Website:
- Copy the HTML code into your website
- Or link directly to the HTML file
- Test by submitting a form

### D. Import Submission into App:
1. Copy the email from Web3Forms
2. Go to **📥 Import Leads**
3. Go to **"2️⃣ Web3Forms Email Paste"**
4. Paste email and click **"Parse & Import"**
5. Lead is now in your database

---

## Next Steps

### Today:
✅ Test with sample data  
✅ Try generating messages  
✅ Export a report  

### This Week:
✅ Set up Web3Forms on your website  
✅ Create and test the HTML form  
✅ Import your first real leads  

### This Month:
✅ Daily lead check-ins  
✅ Send first outreach batches  
✅ Track follow-ups  
✅ Close first sales!  

---

## Key Features to Know

### 🔥 Hot Leads
- **Score ≥ 70** = reach out ASAP
- Dashboard shows them first

### 📧 Outreach Types
- **cold_email** – Initial contact
- **reply_to_inbound** – Response to inquiry
- **phone_opener** – Script for calling
- **trial_offer** – Invite for 7-day trial
- **follow_up_education** – How the product works
- **social_proof** – Case study reference

### 📤 Export Options
- **All Leads** – CSV for backup
- **Hot Leads** – High-scoring only
- **Call List** – Phone numbers to dial
- **Approved Emails** – Copy to Gmail

### 💾 Your Data
- Everything is **local** (no cloud)
- Stored in `aquelyst_hunter.db`
- Backup anytime: `cp aquelyst_hunter.db aquelyst_hunter.db.backup`

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Command not found: streamlit" | Run: `pip install -r requirements.txt` |
| "Python 3.11+ required" | Install Python 3.11 or newer |
| Dashboard won't load | Restart: `Ctrl+C` then `python3 run_app.py` |
| Can't import CSV | Verify columns: `business_name`, `email` required |
| Web3Forms form not working | Check Access Key is correct in HTML |

---

## Need Help?

1. Check **README.md** for detailed docs
2. Review code comments in each Python file
3. Look at `sample_leads.csv` for data format examples

---

## Ready to Sell? 

**You now have everything to:**
- 📥 Capture website leads
- 🎯 Score and prioritize them
- 📧 Generate personalized outreach
- 📋 Track follow-ups
- 📊 Monitor conversion rate
- 💰 Close sales

**Let's go!** 🚀
