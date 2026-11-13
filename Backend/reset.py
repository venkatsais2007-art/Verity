from db import get_conn

c = get_conn()
c.execute("UPDATE submissions SET status='draft', review_progress=NULL WHERE status='ai_review'")
c.commit()
c.close()
print("reset done")
