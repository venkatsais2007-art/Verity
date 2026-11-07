import sqlite3

conn = sqlite3.connect("verity.db")
conn.row_factory = sqlite3.Row
WEIGHTS = {"high": 15, "medium": 8, "low": 3}

T = {
    "miracle": ("high", "terminology", "miracle", "'miracle' is a banned word in the brand terminology.",
                "Preferred Terminology: banned words include 'miracle'", "Remove 'miracle' and state the benefit factually."),
    "best": ("high", "terminology", "best in the world", "'best in the world' is a banned superlative claim.",
             "Preferred Terminology: banned words include 'best in the world'", "Remove the superlative and describe a verified benefit."),
    "guaranteed": ("high", "terminology", "guaranteed", "'guaranteed' is a banned word.",
                   "Preferred Terminology: banned words include 'guaranteed'", "Remove 'guaranteed'."),
    "detox": ("high", "terminology", "detox", "'detox' is a banned word.",
              "Preferred Terminology: banned words include 'detox'", "Remove 'detox' and describe the product factually."),
    "price29": ("high", "outdated_facts", "$29", "This price is outdated.",
                "Approved Claims and Evidence: the current price is $39 per month; $29 is outdated", "Use the current price ($39 per month)."),
    "clinical": ("high", "claims", "clinically proven", "The 18% figure is a self-reported internal survey, not a clinical study.",
                 "Approved Claims and Evidence: describe it as a self-reported internal survey", "Say 'in an internal survey of 120 members, 18% reported higher energy (self-reported)'."),
    "customers": ("low", "terminology", "customers", "The brand prefers 'members' over 'customers'.",
                  "Preferred Terminology: use 'members', not 'customers'", "Replace 'customers' with 'members'."),
    "thedaily": ("medium", "terminology", "the Daily", "The product name must be written in full.",
                 "Preferred Terminology: always 'Northwind Daily', never 'the Daily'", "Use 'Northwind Daily'."),
    "worldwide": ("medium", "messaging", "worldwide", "Northwind is only available in the US and Canada.",
                  "Approved Company Facts: available in the US and Canada only", "Say 'available in the US and Canada'."),
    "competitor": ("medium", "tone", "Unlike Brand X", "Content must not compare Northwind with named competitors.",
                   "Tone Rules: do not compare ourselves to named competitors", "Remove the comparison."),
    "excl": ("low", "tone", "Don't miss out!!!", "More than one exclamation mark is used.",
             "Brand Voice: use at most one exclamation mark per post", "Keep a single exclamation mark."),
    "caps": ("medium", "tone", "ORDER NOW", "ALL CAPS reads as shouting.",
             "Tone Rules: do not use ALL CAPS for emphasis", "Write it in sentence case."),
}

CAPS_R = "Campaign call to action uses caps in the approved ad template"
EXCL_R = "Sale event needs excitement, approved by marketing"

SAMPLES = [
    dict(creator="creator02", title="Spring sale ad", channel="ad", purpose="Drive spring sales", status="published",
         v1="Unlike Brand X, our miracle Northwind Daily is guaranteed to work. Only $29 per month. Don't miss out!!! ORDER NOW",
         v2="Northwind Daily gives members 12 vitamins and minerals. Now $39 per month, with free shipping over $40. Order today.",
         findings=[("competitor", "accepted", ""), ("miracle", "accepted", ""), ("guaranteed", "accepted", ""),
                   ("price29", "accepted", ""), ("excl", "edited", ""), ("caps", "dismissed", CAPS_R)]),
    dict(creator="creator01", title="Energy boost post", channel="social", purpose="Share the energy survey result", status="published",
         v1="Our customers say Northwind Daily is the best in the world and clinically proven to boost energy by 18%!",
         v2="Members tell us Northwind Daily fits their morning routine. In an internal survey of 120 members, 18% reported higher energy (self-reported).",
         findings=[("customers", "accepted", ""), ("best", "accepted", ""), ("clinical", "accepted", "")]),
    dict(creator="creator03", title="Welcome email", channel="email", purpose="Welcome new members", status="approved",
         v1="Welcome! Northwind customers get free shipping worldwide. Try the Daily today!",
         v2="Welcome! Northwind members get free shipping on orders over $40 in the US and Canada. Try Northwind Daily today.",
         findings=[("customers", "accepted", ""), ("worldwide", "accepted", ""), ("thedaily", "edited", "")]),
    dict(creator="creator02", title="Retargeting ad", channel="ad", purpose="Win back site visitors", status="rejected",
         v1="Detox with our miracle Northwind Daily. Guaranteed results or your money back. Unlike Brand Y, we actually work!!!",
         findings=[("detox", "accepted", "", "Detox"), ("miracle", "accepted", ""),
                   ("guaranteed", "dismissed", "Money-back offer is a real policy", "Guaranteed"),
                   ("competitor", "dismissed", "Comparison is based on public data", "Unlike Brand Y"),
                   ("excl", "accepted", "", "work!!!")]),
    dict(creator="creator01", title="Weekend promo", channel="social", purpose="Promote the weekend free shipping offer", status="in_human_review",
         v1="Big weekend sale! Free shipping on orders over $40! Northwind Daily is back at $39 per month.",
         findings=[("excl", "dismissed", EXCL_R, "Free shipping on orders over $40!")]),
    dict(creator="creator02", title="Brand comparison ad", channel="ad", purpose="Position against a competitor", status="needs_changes",
         v1="Unlike Brand X, Northwind Daily is the Daily that actually works. A clinical study showed 18% more energy. Available worldwide.",
         findings=[("competitor", "open", ""), ("thedaily", "open", ""), ("clinical", "open", "", "clinical study"),
                   ("worldwide", "open", "")]),
    dict(creator="creator03", title="Newsletter October", channel="email", purpose="Monthly newsletter offer", status="in_human_review",
         v1="Hi there, our customers love Northwind Daily. DON'T MISS THE OCTOBER OFFER and enjoy free shipping.",
         findings=[("customers", "edited", ""),
                   ("caps", "dismissed", "Newsletter banner style is part of the template", "DON'T MISS THE OCTOBER OFFER")]),
    dict(creator="creator01", title="Morning routine page", channel="web", purpose="Landing page copy", status="approved",
         v1="Northwind Daily is a miracle for busy mornings. Learn more.",
         v2="Northwind Daily fits busy mornings. Learn more.",
         findings=[("miracle", "accepted", "")]),
    dict(creator="creator02", title="Holiday offer ad", channel="ad", purpose="Holiday promotion", status="published",
         v1="Guaranteed best price! Only $29 per month. ORDER NOW",
         v2="Northwind Daily is now $39 per month with free shipping over $40. Order today.",
         findings=[("guaranteed", "accepted", "", "Guaranteed"), ("price29", "accepted", ""), ("caps", "dismissed", CAPS_R)]),
    dict(creator="creator02", title="Lookalike ad", channel="ad", purpose="Reach lookalike audiences", status="needs_changes",
         v1="Our miracle blend is better than Brand Z. ORDER NOW. Clinically proven.",
         findings=[("miracle", "open", ""), ("competitor", "open", "", "better than Brand Z"), ("caps", "open", ""),
                   ("clinical", "open", "", "Clinically proven")]),
    dict(creator="creator03", title="Reactivation email", channel="email", purpose="Re-engage lapsed members", status="published",
         v1="Come back! Our customers save with free shipping worldwide.",
         v2="Come back! Members get free shipping on orders over $40 in the US and Canada.",
         findings=[("customers", "accepted", ""), ("worldwide", "accepted", "")]),
    dict(creator="creator01", title="Launch teaser", channel="social", purpose="Teaser for the new product page", status="published",
         v1="Don't miss out!!! The Daily is here.",
         v2="Northwind Daily is here. Meet your new morning routine!",
         findings=[("excl", "dismissed", EXCL_R), ("thedaily", "accepted", "")]),
]

if conn.execute("SELECT 1 FROM submissions WHERE title='Spring sale ad'").fetchone():
    print("Demo data was already added.")
    raise SystemExit

cid = conn.execute("SELECT id FROM companies WHERE code='NORTHWIND'").fetchone()["id"]
users = {r["employee_id"]: r["id"] for r in conn.execute("SELECT id, employee_id FROM users WHERE company_id=?", (cid,))}
manager = users["manager01"]
total = len(SAMPLES)

for i, s in enumerate(SAMPLES):
    ts = f"-{total - i} days"
    creator = users[s["creator"]]
    fl = []
    for f in s["findings"]:
        sev, cat, ft, why, ref, fix = T[f[0]]
        fl.append(dict(sev=sev, cat=cat, ft=(f[3] if len(f) > 3 else ft), why=why, ref=ref, fix=fix,
                       decision=f[1], reason=f[2]))
    score = max(0, 100 - sum(WEIGHTS[x["sev"]] for x in fl))
    worst = "high" if any(x["sev"] == "high" for x in fl) else ("medium" if any(x["sev"] == "medium" for x in fl) else "low")
    two = s["status"] in ("approved", "published")
    risk = "low" if two else worst

    sid = conn.execute(
        "INSERT INTO submissions (company_id, creator_id, title, channel, purpose, status, current_version, risk_level, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,datetime('now',?),datetime('now',?))",
        (cid, creator, s["title"], s["channel"], s["purpose"], s["status"], 2 if two else 1, risk, ts, ts)).lastrowid
    conn.execute(
        "INSERT INTO submission_versions (submission_id, version, content, file_type, score, created_at) "
        "VALUES (?,?,?,'text',?,datetime('now',?))", (sid, 1, s["v1"], score, ts))
    if two:
        conn.execute(
            "INSERT INTO submission_versions (submission_id, version, content, file_type, score, created_at) "
            "VALUES (?,?,?,'text',100,datetime('now',?))", (sid, 2, s["v2"], ts))
    for x in fl:
        decided = x["decision"] != "open"
        conn.execute(
            "INSERT INTO findings (submission_id, version, severity, category, flagged_text, reason, source_ref, suggestion, "
            "decision, decision_reason, decided_by, decided_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now',?))",
            (sid, 1, x["sev"], x["cat"], x["ft"], x["why"], x["ref"], x["fix"], x["decision"],
             x["reason"] or None, creator if decided else None, ts))

    def a(uid, action, detail=""):
        conn.execute(
            "INSERT INTO audit_log (company_id, submission_id, user_id, action, detail, created_at) "
            "VALUES (?,?,?,?,?,datetime('now',?))", (cid, sid, uid, action, detail, ts))

    a(creator, "submission_created", f"{s['title']} ({s['channel']}, text)")
    a(creator, "sent_for_ai_review", "v1")
    a(None, "ai_review_completed", f"v1: {len(fl)} findings, score {score}, rules only")
    for x in fl:
        if x["decision"] != "open":
            d = f"{x['cat']}: {x['ft'][:80]}"
            if x["reason"]:
                d += f" | reason: {x['reason']}"
            a(creator, f"finding_{x['decision']}", d)
    if two:
        a(creator, "revised", "v2 created by creator, re-check started")
        a(None, "ai_review_completed", "v2: 0 findings, score 100, rules only")
        a(manager, "approved", "")
        if s["status"] == "published":
            a(manager, "published", "Published by Sara Lindqvist (manager)")
    elif s["status"] in ("in_human_review", "rejected"):
        note = "Please review. I kept the flags I disagree with and explained why."
        conn.execute(
            "INSERT INTO comments (submission_id, user_id, body, kind, created_at) VALUES (?,?,?,'escalation',datetime('now',?))",
            (sid, creator, note, ts))
        a(creator, "escalated", "Sent to human review with open flags. Note: " + note)
        if s["status"] == "rejected":
            msg = "Cannot approve: banned claims remain in the copy. Please rewrite without them."
            conn.execute(
                "INSERT INTO comments (submission_id, user_id, body, kind, created_at) VALUES (?,?,?,'rejection',datetime('now',?))",
                (sid, manager, msg, ts))
            a(manager, "rejected", msg)

conn.commit()
print(f"Added {total} demo submissions.")