import sqlite3

c = sqlite3.connect("verity.db")
c.execute("UPDATE submissions SET status='draft', review_progress=NULL WHERE status='ai_review'")
c.commit()
print("reset done")