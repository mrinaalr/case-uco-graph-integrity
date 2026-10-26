"""Generate synthetic fraud/business-communication cases with gold graphs.

For each case the gold graph is authored first, then rendered to 2-4 short
documents. Every gold triple is assigned to exactly one sentence span. Key
literals (names, addresses, account numbers) are anchored at the first
sentence that spells them out; later mentions are references, not restatements.

    python harness/generate_data.py [--cases 30] [--seed 20251025] [--validate]
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from graphkit import HARNESS, GraphWriter, case_validate, expand, graph_triples, iso_time, kb_id

FIRST = ["Dana", "Marcus", "Priya", "Owen", "Lena", "Tomas", "Grace", "Hector", "Nadia", "Victor",
         "Elena", "Samuel", "Irene", "Kofi", "Maya", "Felix", "Rosa", "Arjun", "Clara", "Desmond",
         "Yara", "Luca", "Hannah", "Julian", "Mei", "Oscar", "Ruth", "Andre", "Sofia", "Wesley"]
LAST = ["Reyes", "Whitfield", "Banerjee", "Kowalski", "Osei", "Lindqvist", "Moreau", "Tanaka",
        "Castillo", "Brennan", "Haddad", "Novak", "Okafor", "Fischer", "Delgado", "Ashworth",
        "Ivanova", "Mendes", "Park", "Sorensen", "Quinn", "Abara", "Holloway", "Vance", "Petrov"]
ORG_A = ["Northwind", "Bluegate", "Cedar Ridge", "Harborline", "Ironleaf", "Summit Peak", "Copperfield",
         "Brightwater", "Stonebridge", "Redfern", "Silverlake", "Oakhaven", "Westmark", "Clearpath"]
ORG_B = ["Logistics", "Supply", "Industrial", "Consulting", "Packaging", "Freight", "Components",
         "Analytics", "Fabrication", "Services", "Distribution", "Tooling"]
ORG_C = ["LLC", "Inc.", "Group", "Ltd.", "Co."]
BANKS = ["First Harbor Bank", "Granite Federal Credit Union", "Meridian Trust Bank", "Lakeshore Savings Bank",
         "Pinecrest National Bank", "Union Ledger Bank"]
CITIES = [("Dayton", "OH", "45402"), ("Spokane", "WA", "99201"), ("Raleigh", "NC", "27601"),
          ("Tucson", "AZ", "85701"), ("Madison", "WI", "53703"), ("Albany", "NY", "12207"),
          ("Boise", "ID", "83702"), ("Omaha", "NE", "68102"), ("Richmond", "VA", "23219")]
STREETS = ["Main Street", "Harbor Avenue", "Elm Street", "Commerce Drive", "Lakeview Road",
           "Market Street", "Industrial Parkway", "Maple Avenue", "Riverside Boulevard"]
EVENT_TYPES = ["vendor onboarding", "bank detail change", "invoice submission", "payment approval",
               "wire transfer", "account reconciliation", "audit review", "refund request",
               "contract amendment", "expense reimbursement"]
APPROVAL_TYPES = {"payment approval", "wire transfer", "bank detail change", "refund request",
                  "contract amendment", "expense reimbursement"}
SUBJECTS = ["Updated remittance details", "Invoice {n} follow-up", "Urgent: payment timing",
            "Quarter-end vendor payments", "Re: banking change request", "Wire confirmation needed",
            "Contract terms for next quarter", "Audit prep items"]
CHAT_LINES = ["Can you look at the vendor file before lunch?", "Did the bank call back yet?",
              "Let's keep this between us until Friday.", "I pushed it through, check your inbox.",
              "Finance is asking questions again.", "Send me the new form when you can."]
FILLER = ["Please treat this as confidential.", "Let me know if anything here looks off.",
          "More detail will follow once records are pulled.", "This summary reflects records available to date."]

# Gold property -> facet that carries it (None = property sits on the object).
FACET = {
    ("EmailAddress", "addressValue"): "EmailAddressFacet",
    ("Account", "accountIdentifier"): "AccountFacet", ("Account", "accountIssuer"): "AccountFacet",
    ("Account", "accountType"): "AccountFacet", ("EmailAccount", "emailAddress"): "EmailAccountFacet",
    ("ApplicationAccount", "accountIdentifier"): "AccountFacet",
    **{("Location", p): "SimpleAddressFacet" for p in ("street", "locality", "region", "postalCode")},
    **{("EmailMessage", p): "EmailMessageFacet" for p in ("from", "to", "subject", "sentTime")},
    **{("Message", p): "MessageFacet" for p in ("from", "to", "messageText", "sentTime")},
}
KEY_PROPS = {"name", "addressValue", "accountIdentifier"}


def fmt_long(dt: datetime, rng: random.Random) -> str:
    return rng.choice([f"{dt:%B} {dt.day}, {dt.year} at {dt:%H:%M} UTC", f"{dt.day} {dt:%B %Y}, {dt:%H:%M} UTC"])


class Case:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.entities: dict[str, dict] = {}
        self.triples: list[dict] = []
        self.names: dict[str, str] = {}

    def entity(self, eid: str, cls: str, label: str | None = None) -> str:
        self.entities[eid] = {"eid": eid, "class": cls}
        if label:
            self.names[eid] = label
        return eid

    def triple(self, s: str, p: str, o, lit: bool = True) -> str:
        tid = f"t{len(self.triples) + 1}"
        self.triples.append({"tid": tid, "s": s, "p": p, "o": o, "lit": lit})
        return tid

    def rel(self, s: str, kind: str, o: str) -> str:
        return self.triple(s, kind, o, lit=False)


def build_case(idx: int, seed: int) -> dict:
    rng = random.Random(f"{seed}-{idx}")
    c = Case(rng)
    t0 = datetime(2025, rng.randint(1, 10), rng.randint(1, 20), 9, 0, tzinfo=timezone.utc)
    first, last = rng.sample(FIRST, 6), rng.sample(LAST, 6)
    org_names = rng.sample(ORG_A, 2)

    def org(eid: str, base: str) -> tuple[str, str]:
        name = f"{base} {rng.choice(ORG_B)} {rng.choice(ORG_C)}"
        c.entity(eid, "Organization", name)
        c.triple(eid, "name", name)
        return eid, base.lower().replace(" ", "") + ".com"

    company, company_domain = org("org_company", org_names[0])
    vendor, vendor_domain = org("org_vendor", org_names[1])
    bank = c.entity("org_bank", "Organization", rng.choice(BANKS))
    c.triple(bank, "name", c.names[bank])

    def location(eid: str) -> str:
        city, region, postal = rng.choice(CITIES)
        street = f"{rng.randint(10, 9800)} {rng.choice(STREETS)}"
        c.entity(eid, "Location", f"{street}, {city}, {region} {postal}")
        tids = [c.triple(eid, "street", street), c.triple(eid, "locality", city),
                c.triple(eid, "region", region), c.triple(eid, "postalCode", postal)]
        c.entities[eid]["address_tids"] = tids
        return eid

    n_people, n_events = rng.randint(3, 5), rng.randint(3, 8)
    n_docs = rng.choice([2, 3, 3, 4])
    doc_types = {2: [["memo", "email"]],
                 3: [["memo", "email", "report"], ["memo", "email", "chat"], ["email", "memo", "email"]],
                 4: [["memo", "email", "chat", "report"], ["email", "memo", "email", "report"]]}[n_docs]
    doc_types = rng.choice(doc_types)

    people, emails = [], {}
    for i in range(n_people):
        pid = c.entity(f"person_{i}", "Person", f"{first[i]} {last[i]}")
        c.triple(pid, "name", c.names[pid])
        people.append(pid)
    employer = {p: company for p in people}
    employer[people[-1]] = vendor
    if n_people == 5:
        employer[people[-2]] = vendor
    insiders = [p for p in people if employer[p] == company]

    mandatory, optional = [], []  # prose facts: (kind, payload)
    for p in people:
        domain = company_domain if employer[p] == company else vendor_domain
        fn, ln = c.names[p].lower().split()
        addr = rng.choice([f"{fn}.{ln}@{domain}", f"{fn[0]}{ln}@{domain}"])
        eid = c.entity(f"email_{p}", "EmailAddress", addr)
        c.triple(eid, "addressValue", addr)
        emails[p] = eid
        mandatory.append(("staff", [c.rel(p, "Employed_By", employer[p]), c.rel(p, "Holds_Account", eid)], [p, employer[p], eid]))

    hq = location("loc_company")
    mandatory.append(("located", [c.rel(company, "Located_At", hq)], [company, hq]))
    optional.append(("vendor_loc", None, None))

    accounts = []
    for eid, owner in [("acct_company", company), ("acct_vendor", vendor)] + (
            [("acct_insider", rng.choice(insiders))] if rng.random() < 0.6 else []):
        c.entity(eid, "Account")
        number = str(rng.randint(10**9, 10**10 - 1))
        c.names[eid] = number
        c.triple(eid, "accountIdentifier", number)
        mandatory.append(("account", [c.rel(owner, "Owns_Account", eid), c.triple(eid, "accountIssuer", bank, lit=False)],
                          [owner, eid, bank]))
        accounts.append(eid)

    etypes = rng.sample(EVENT_TYPES, n_events)
    times = sorted(t0 + timedelta(days=rng.randint(0, 40), hours=rng.randint(0, 8), minutes=rng.choice([0, 10, 15, 25, 30, 45, 50]))
                   for _ in range(n_events))
    events = []
    for i, (etype, when) in enumerate(zip(etypes, times)):
        ev = c.entity(f"event_{i}", "Event", etype)
        init = rng.choice(people)
        c.entities[ev]["when"] = when
        main = [c.triple(ev, "eventType", etype), c.triple(ev, "startTime", when.strftime("%Y-%m-%dT%H:%M:%SZ")),
                c.rel(init, "Initiated", ev)]
        mandatory.append(("event", main, [ev, init]))
        events.append(ev)
        others = rng.sample([p for p in people if p != init], 2)
        if etype in APPROVAL_TYPES:
            optional.append(("authorized", (others[0], ev), None))
        optional.append(("participated", (others[1], ev), None))
        optional.append(("event_loc", ev, None))
    for sub in rng.sample(insiders[1:], min(len(insiders) - 1, 2)):
        optional.append(("reports_to", (sub, insiders[0]), None))
    src = "acct_company"
    for dst in rng.sample([a for a in accounts if a != src], min(2, len(accounts) - 1)):
        optional.append(("transfer", (src, dst), None))
    optional.append(("comm", tuple(rng.sample(people, 2)), None))

    # Chat handles are required by the chat document's messages.
    handles = {}
    if "chat" in doc_types:
        for p in rng.sample(people, 2):
            fn, ln = c.names[p].lower().split()
            h = f"@{fn}{ln[0]}"
            hid = c.entity(f"handle_{p}", "ApplicationAccount", h)
            c.triple(hid, "accountIdentifier", h)
            handles[p] = (hid, c.rel(p, "Holds_Account", hid))

    rel_count = sum(1 for t in c.triples if not t["lit"] and t["p"][0].isupper())
    rng.shuffle(optional)
    cap = rng.randint(max(10, rel_count), 25)
    chosen = []
    for kind, payload, _ in optional:
        if rel_count + 1 > cap:
            continue
        if kind == "vendor_loc":
            loc = location("loc_vendor")
            chosen.append(("located", [c.rel(vendor, "Located_At", loc)], [vendor, loc]))
        elif kind == "authorized":
            p, ev = payload
            chosen.append(("authorized", [c.rel(p, "Authorized", ev)], [p, ev]))
        elif kind == "participated":
            p, ev = payload
            chosen.append(("participated", [c.rel(p, "Participated_In", ev)], [p, ev]))
        elif kind == "event_loc":
            chosen.append(("event_loc", [c.rel(payload, "Located_At", hq)], [payload, hq, company]))
        elif kind == "reports_to":
            chosen.append(("reports_to", [c.rel(payload[0], "Reports_To", payload[1])], list(payload)))
        elif kind == "transfer":
            chosen.append(("transfer", [c.rel(payload[0], "Transferred_To", payload[1])], list(payload)))
        elif kind == "comm":
            chosen.append(("comm", [c.rel(payload[0], "Communicated_With", payload[1])], list(payload)))
        rel_count += 1
    facts = mandatory + chosen
    docs = render(c, doc_types, facts, people, emails, handles, events, company)
    authored = sum(1 for t in c.triples if not t["lit"] and t["p"][0].isupper())
    derive_stated(c, docs)
    return finalize(c, idx, docs, authored)


def derive_stated(c: Case, docs: list[dict]) -> None:
    """Add facts the rendered text states but the authored graph lacks.

    Uses no randomness, so the documents do not change. Each fact goes on the
    sentence that states it: chat and email exchanges as Communicated_With,
    the chat channel as a MessageThread, "account ... at <bank>" as a bank
    account type, and each staff address as an EmailAccount the person holds.
    """
    cls = lambda eid: c.entities[eid]["class"]
    owner = {t["o"]: t["s"] for t in c.triples if t["p"] == "Holds_Account"}  # address or handle -> person
    have = {(t["s"], t["p"], t["o"]) for t in c.triples}

    def add(sent, s, p, o, lit=False):
        if (s, p, o) not in have:
            have.add((s, p, o))
            sent["tids"].append(c.triple(s, p, o, lit=lit))

    for d in docs:
        for sent in d["sents"]:
            m = sent["mentions"]
            if sent["text"].startswith("Chat export: "):
                c.entity("chat_thread", "MessageThread", sent["text"].split(": ", 1)[1])
                add(sent, "chat_thread", "name", c.names["chat_thread"], lit=True)
                m.append("chat_thread")
            elif len(m) == 3 and cls(m[0]) == "Person" and cls(m[2]) == "EmailAddress":  # staff sentence
                acct = c.entity(f"email_account_{m[0]}", "EmailAccount")
                add(sent, acct, "emailAddress", m[2])
                add(sent, m[0], "Holds_Account", acct)
                m.append(acct)
            elif len(m) == 3 and cls(m[1]) == "Account":  # "account N at <bank>"
                add(sent, m[1], "accountType", "bank account", lit=True)
            elif len(m) == 3 and cls(m[0]) == "Message":  # chat line: sender handle to recipient handle
                add(sent, owner[m[1]], "Communicated_With", owner[m[2]])
            elif m and cls(m[0]) == "EmailMessage" and sent["text"].startswith("To: "):
                sender = next(t["o"] for t in c.triples if t["s"] == m[0] and t["p"] == "from")
                for rcpt in m[1:]:
                    add(sent, owner[sender], "Communicated_With", owner[rcpt])


def render(c: Case, doc_types, facts, people, emails, handles, events, company):
    """Turn facts into documents made of sentence records {text, tids, mentions, brk}."""
    rng, n = c.rng, c.names
    first = {p: n[p].split()[0] for p in people}
    docs = [{"doc_id": f"D{i + 1}", "type": t, "sents": []} for i, t in enumerate(doc_types)]
    by_type = {}
    for d in docs:
        by_type.setdefault(d["type"], []).append(d)

    def add(doc, text, tids=(), mentions=(), brk=" "):
        if doc.pop("para_next", False):
            brk = "\n\n"
        text = text[:-1] if text.endswith("..") else text
        doc["sents"].append({"text": text, "tids": list(tids), "mentions": list(mentions), "brk": brk})

    def para(doc):
        if doc["sents"]:
            doc["para_next"] = True

    by_kind: dict[str, list] = {}
    for kind, tids, mentions in facts:
        by_kind.setdefault(kind, []).append((tids, mentions))

    def addr_text(loc):
        return n[loc]

    def staff(doc, tids, m):
        p, org, mail = m
        add(doc, rng.choice(["{p} works for {o} and uses the address {e}.", "{p} is employed by {o}; their email is {e}.",
                             "{o} employs {p}, who can be reached at {e}."]).format(p=n[p], o=n[org], e=n[mail]), tids, m)

    def located(doc, tids, m):
        org, loc = m
        add(doc, rng.choice(["{o} operates from {a}.", "{o} is based at {a}.", "The offices of {o} are at {a}."]).format(
            o=n[org], a=addr_text(loc)), tids + c.entities[loc]["address_tids"], m)

    def account(doc, tids, m):
        owner, acct, issuer = m
        add(doc, rng.choice(["{o} holds account {a} at {b}.", "Account {a} at {b} belongs to {o}.",
                             "{b} account {a} is registered to {o}."]).format(o=n[owner], a=n[acct], b=n[issuer]), tids, m)

    def event(doc, tids, m):
        ev, init = m
        when = fmt_long(c.entities[ev]["when"], rng)
        add(doc, rng.choice(["{p} started the {t} on {w}.", "On {w}, {p} initiated the {t}.",
                             "The {t} was initiated by {p} on {w}."]).format(p=n[init], t=n[ev], w=when), tids, m)
        for kind, tmpl in (("authorized", ["{p} authorized the {t}.", "Approval for the {t} came from {p}."]),
                           ("participated", ["{p} also took part in the {t}.", "{p} was involved in the {t} as well."]),
                           ("event_loc", ["The {t} took place at the {o} office.", "The {t} happened at {o}'s office."])):
            for etids, em in by_kind.get(kind, []):
                if em[0 if kind == "event_loc" else 1] == ev:
                    other = em[0]
                    add(doc, rng.choice(tmpl).format(p=n.get(other, ""), t=n[ev], o=n[company]), etids, em)

    def reports_to(doc, tids, m):
        add(doc, rng.choice(["{a} reports to {b}.", "{a}'s manager is {b}."]).format(a=n[m[0]], b=n[m[1]]), tids, m)

    def transfer(doc, tids, m):
        add(doc, rng.choice(["Funds moved from account {a} to account {b}.", "Account {a} sent a transfer to account {b}."]).format(
            a=n[m[0]], b=n[m[1]]), tids, m)

    def comm(doc, tids, m):
        add(doc, rng.choice(["{a} had been in contact with {b} throughout.", "{a} communicated with {b} about the payments."]).format(
            a=n[m[0]], b=n[m[1]]), tids, m)

    memo = by_type["memo"][0]
    report = by_type.get("report", [None])[0]
    email_docs = by_type.get("email", [])
    prose_docs = email_docs + ([report] if report else []) + [memo]

    add(memo, "INTERNAL MEMO: Vendor payment review", brk="\n")
    for kind, fn in (("staff", staff), ("reports_to", reports_to), ("located", located)):
        para(memo)
        for tids, m in by_kind.get(kind, []):
            fn(memo, tids, m)
    if report:
        add(report, "Incident summary", brk="\n")
    para(report or memo)
    for tids, m in by_kind.get("account", []):
        account(report or memo, tids, m)
    event_items = by_kind.get("event", [])
    targets = [d for d in prose_docs if d["type"] != "memo"] or [memo]
    body: dict[str, list] = {d["doc_id"]: [] for d in prose_docs}
    for i, item in enumerate(event_items):
        body[targets[i % len(targets)]["doc_id"]].append(("event", item))
    for item in by_kind.get("transfer", []):
        body[(report or memo)["doc_id"]].append(("transfer", item))
    for item in by_kind.get("comm", []):
        body[rng.choice(prose_docs)["doc_id"]].append(("comm", item))

    for d in prose_docs:
        if d["type"] == "email":
            continue
        para(d)
        for kind, (tids, m) in body[d["doc_id"]]:
            {"event": event, "transfer": transfer, "comm": comm}[kind](d, tids, m)
        para(d)
        add(d, rng.choice(FILLER))

    senders = [p for p in people if p in emails]
    for k, d in enumerate(email_docs):
        mid = c.entity(f"email_msg_{k}", "EmailMessage")
        sender = rng.choice(senders)
        rcpts = rng.sample([p for p in people if p != sender], rng.choice([1, 2]))
        own_events = [m[0] for kind, (t, m) in body[d["doc_id"]] if kind == "event"]
        sent = (c.entities[own_events[-1]]["when"] if own_events else datetime(2025, 11, 3, 9, tzinfo=timezone.utc)) + timedelta(hours=2)
        subject = rng.choice(SUBJECTS).format(n=rng.randint(1000, 9999))
        add(d, f"From: {n[emails[sender]]}", [c.triple(mid, "from", emails[sender], lit=False)], [mid, emails[sender]], brk="\n")
        add(d, "To: " + ", ".join(n[emails[r]] for r in rcpts),
            [c.triple(mid, "to", emails[r], lit=False) for r in rcpts], [mid] + [emails[r] for r in rcpts], brk="\n")
        add(d, f"Subject: {subject}", [c.triple(mid, "subject", subject)], [mid], brk="\n")
        add(d, f"Date: {sent:%a, %d %b %Y %H:%M:%S} +0000", [c.triple(mid, "sentTime", sent.strftime("%Y-%m-%dT%H:%M:%SZ"))], [mid], brk="\n")
        add(d, f"Hi {first[rcpts[0]]},", brk="\n\n")
        start = len(d["sents"])
        for kind, (tids, m) in body[d["doc_id"]]:
            {"event": event, "transfer": transfer, "comm": comm}[kind](d, tids, m)
        if len(d["sents"]) == start:
            add(d, rng.choice(FILLER))
        d["sents"][start]["brk"] = "\n\n"
        add(d, "Thanks,", brk="\n\n")
        add(d, first[sender], brk="\n")

    for d in by_type.get("chat", []):
        add(d, "Chat export: #finance-ops", brk="\n")
        for p, (hid, htid) in handles.items():
            add(d, f"{n[hid]} is {n[p]}.", [htid], [hid, p], brk="\n")
        pair = list(handles)
        base = c.entities[events[0]]["when"]
        for k in range(rng.randint(1, 3)):
            mid = c.entity(f"chat_msg_{k}", "Message")
            a, b = pair[k % 2], pair[(k + 1) % 2]
            when = base + timedelta(hours=1, minutes=7 * k)
            text = CHAT_LINES[(k + len(c.triples)) % len(CHAT_LINES)]
            tids = [c.triple(mid, "from", handles[a][0], lit=False), c.triple(mid, "to", handles[b][0], lit=False),
                    c.triple(mid, "sentTime", when.strftime("%Y-%m-%dT%H:%M:%SZ")), c.triple(mid, "messageText", text)]
            add(d, f"[{when:%Y-%m-%d %H:%M} UTC] {n[handles[a][0]]} to {n[handles[b][0]]}: {text}", tids,
                [mid, handles[a][0], handles[b][0]], brk="\n")
    return docs


def finalize(c: Case, idx: int, docs: list[dict], authored_rels: int) -> dict:
    spans, doc_texts = {}, {}
    order = []
    for d in docs:
        text, marked = "", []
        for i, s in enumerate(d["sents"]):
            sid = f"{d['doc_id']}.S{i + 1}"
            sep = "" if not text else s["brk"]
            start = len(text) + len(sep)
            text += sep + s["text"]
            marked.append(("" if not marked else s["brk"]) + f"[{sid}] {s['text']}")
            spans[sid] = {"doc_id": d["doc_id"], "start": start, "end": start + len(s["text"]), "text": s["text"],
                          "tids": list(s["tids"]), "mentions": list(s["mentions"])}
            order.append(sid)
        doc_texts[d["doc_id"]] = {"type": d["type"], "text": text, "marked": "".join(marked)}

    # Anchor key literals at the first span that spells them out.
    assigned = {t: sid for sid in order for t in spans[sid]["tids"]}
    for t in c.triples:
        if t["tid"] in assigned:
            continue
        if t["p"] in KEY_PROPS:
            sid = next((s for s in order if t["o"] in spans[s]["text"]), None)
            if sid:
                spans[sid]["tids"].append(t["tid"])
                assigned[t["tid"]] = sid
    missing = [t for t in c.triples if t["tid"] not in assigned]
    assert not missing, f"case {idx}: triples without a span: {missing}"
    counts = {}
    for sid in order:
        for t in spans[sid]["tids"]:
            counts[t] = counts.get(t, 0) + 1
    assert all(v == 1 for v in counts.values()), f"case {idx}: triple in more than one span"
    for t in c.triples:
        t["span_id"] = assigned[t["tid"]]
        t["doc_id"] = spans[t["span_id"]]["doc_id"]
        if t["lit"] and t["p"] not in ("startTime", "sentTime", "accountType"):  # "bank account" is implied by "at <bank>"
            assert t["o"] in spans[t["span_id"]]["text"], (idx, t)

    # Documents in which each entity is mentioned.
    for e in c.entities.values():
        label = c.names.get(e["eid"])
        e["docs"] = sorted({spans[s]["doc_id"] for s in order
                            if e["eid"] in spans[s]["mentions"] or (label and label in spans[s]["text"])
                            or any(x["s"] == e["eid"] for x in c.triples if x["tid"] in spans[s]["tids"])})
        e["label"] = label
        e.pop("when", None)
        e.pop("address_tids", None)

    rels = sum(1 for t in c.triples if not t["lit"] and t["p"][0].isupper())
    n_events = sum(1 for e in c.entities.values() if e["class"] == "Event")
    assert 10 <= authored_rels <= 25 and 3 <= n_events <= 8, (idx, authored_rels, n_events)
    return {"case_id": f"case_{idx:02d}", "entities": list(c.entities.values()), "triples": c.triples,
            "spans": spans, "documents": doc_texts, "relationship_count": authored_rels,
            "relationship_count_total": rels}


def to_graph(case: dict) -> GraphWriter:
    b = GraphWriter()
    node_props: dict[str, dict] = {}
    facet_props: dict[tuple, dict] = {}
    ents = {e["eid"]: e for e in case["entities"]}
    for t in case["triples"]:
        if t["p"][0].isupper():
            continue
        facet = FACET.get((ents[t["s"]]["class"], t["p"]))
        bucket = facet_props.setdefault((t["s"], facet), {}) if facet else node_props.setdefault(t["s"], {})
        if t["p"] == "to":
            bucket.setdefault("to", []).append(t["o"])
        else:
            bucket[t["p"]] = t["o"]
    for eid, e in ents.items():
        b.add_node(eid, e["class"], node_props.get(eid))
    for (eid, facet), props in facet_props.items():
        b.add_facet(eid, facet, props)
    for t in case["triples"]:
        if t["p"][0].isupper():
            b.add_relationship(t["s"], t["o"], t["p"])
    return b


def check_roundtrip(case: dict, path: Path) -> None:
    """The gold JSON-LD must extract to exactly the gold triples."""
    back = {expand(kb_id(e["eid"])): e["eid"] for e in case["entities"]}
    _, triples = graph_triples(path)
    got = set()
    for t in triples:
        o = (iso_time(t["o"]) if t["p"] in ("startTime", "sentTime") else t["o"]) if t["lit"] else back.get(t["o"], t["o"])
        got.add((back.get(t["s"], t["s"]), t["p"], o))
    want = {(t["s"], t["p"], t["o"]) for t in case["triples"]}
    assert got == want, f"{case['case_id']}: round-trip mismatch {sorted(got ^ want)[:6]}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20251025)
    ap.add_argument("--validate", action="store_true", help="run case_validate on every gold graph")
    args = ap.parse_args()
    out = HARNESS / "data"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for idx in range(1, args.cases + 1):
        case = build_case(idx, args.seed)
        d = out / case["case_id"]
        (d / "docs").mkdir(parents=True)
        for doc_id, doc in case["documents"].items():
            (d / "docs" / f"{doc_id}.txt").write_text(doc["text"] + "\n", encoding="utf-8")
            (d / "docs" / f"{doc_id}.marked.txt").write_text(doc["marked"] + "\n", encoding="utf-8")
        (d / "spans.json").write_text(json.dumps(case["spans"], indent=1), encoding="utf-8")
        gold = {k: case[k] for k in ("case_id", "entities", "triples", "relationship_count", "relationship_count_total")}
        gold["documents"] = {k: v["type"] for k, v in case["documents"].items()}
        gold["seed"] = args.seed
        (d / "gold.json").write_text(json.dumps(gold, indent=1), encoding="utf-8")
        to_graph(case).write(d / "gold.jsonld")
        check_roundtrip(case, d / "gold.jsonld")
        derived = case["relationship_count_total"] - case["relationship_count"]
        msg = (f"{case['case_id']}: {len(case['entities'])} entities, {len(case['triples'])} triples, "
               f"{case['relationship_count']} authored + {derived} derived relationships, {len(case['documents'])} docs")
        if args.validate:
            msg += f", conforms={case_validate(d / 'gold.jsonld')['conforms']}"
        print(msg, flush=True)


if __name__ == "__main__":
    main()
