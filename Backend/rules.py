import re

HIGH_WORDS = {"cure", "guaranteed", "miracle"}


def rule_findings(content, file_type, kb):
    text = content or ""
    out = []

    def add(sev, cat, flagged, reason, ref, fix):
        out.append({"severity": sev, "category": cat, "flagged_text": flagged,
                    "reason": reason, "source_ref": ref, "suggestion": fix})

    # Banned words, read from the knowledge base
    term_title = "Preferred Terminology"
    banned = []
    for r in kb:
        if r["kind"] == "term":
            m = re.search(r"banned words?:\s*([^.]*)", r["content"], re.I)
            if m:
                term_title = r["title"]
                banned += [w.strip(" '\"") for w in m.group(1).split(",") if w.strip()]
    for w in banned:
        m = re.search(r"\b" + re.escape(w) + r"\b", text, re.I)
        if m:
            add("high" if w.lower() in HIGH_WORDS else "medium", "terminology", m.group(0),
                f"'{w}' is a banned word in the brand terminology.",
                f"{term_title}: banned words include '{w}'",
                f"Remove '{w}' and describe the benefit with a specific, factual statement.")

    # Outdated price
    m = re.search(r"\$\s?29\b", text)
    if m:
        add("high", "outdated_facts", m.group(0),
            "This price is outdated. The current price is different.",
            "Approved Claims and Evidence: the current price of Northwind Daily is $39 per month; $29 is outdated",
            "Replace the price with the current approved price ($39 per month).")

    # Clinical claims
    m = re.search(r"clinical(ly)?(\s+(proven|study|trial|tested))?", text, re.I)
    if m:
        add("high", "claims", m.group(0),
            "The 18% figure comes from an internal self-reported survey, not a clinical study.",
            "Approved Claims and Evidence: describe it as a self-reported internal survey, never a clinical study",
            "Say 'in an internal survey of 120 members, 18% reported higher energy (self-reported)'.")

    # Preferred terms
    m = re.search(r"\bcustomers?\b", text, re.I)
    if m:
        add("low", "terminology", m.group(0),
            "The brand prefers 'members' over 'customers'.",
            f"{term_title}: use 'members', not 'customers'",
            "Replace 'customers' with 'members'.")
    m = re.search(r"\bthe Daily\b", text)
    if m:
        add("medium", "terminology", m.group(0),
            "The product name must be written in full.",
            f"{term_title}: always 'Northwind Daily', never 'the Daily'",
            "Use 'Northwind Daily'.")

    # Availability
    m = re.search(r"\b(worldwide|globally|international(ly)?)\b", text, re.I)
    if m:
        add("medium", "messaging", m.group(0),
            "Northwind is only available in the US and Canada.",
            "Approved Company Facts: available in the US and Canada only",
            "Say 'available in the US and Canada'.")

    # Competitor comparison
    m = re.search(r"\b(unlike|better than|versus|vs\.?)\s+[A-Z]\w*(\s+[A-Z0-9]\w*)?", text)
    if m:
        add("medium", "tone", m.group(0),
            "Content must not compare Northwind with named competitors.",
            "Tone Rules: do not compare ourselves to named competitors",
            "Remove the comparison and focus on what Northwind Daily offers.")

    # Exclamation marks
    shouts = re.findall(r"[^.!?\n]*!+", text)
    if len(shouts) > 1:
        add("low", "tone", shouts[1].strip(),
            "More than one exclamation mark is used.",
            "Brand Voice: use at most one exclamation mark per post",
            "Keep a single exclamation mark and use calm, confident wording elsewhere.")

    # ALL CAPS
    m = re.search(r"\b[A-Z]{4,}\b(\s+[A-Z]{3,}\b)*", text)
    if m:
        add("medium", "tone", m.group(0),
            "ALL CAPS reads as shouting.",
            "Tone Rules: do not use ALL CAPS for emphasis",
            "Write it in normal sentence case.")

    # Image alt text
    if file_type == "image" and len(text.strip()) < 20:
        add("medium", "accessibility", text.strip() or "(no alt text)",
            "The image has no descriptive alt text.",
            "Logo Usage: every image needs descriptive alt text",
            "Describe what the image shows in a full sentence.")

    return out