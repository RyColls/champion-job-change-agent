"""Seeded synthetic data generator for the Champion Job-Change Agent proof of concept.

EVERYTHING GENERATED HERE IS FICTIONAL. Company names are invented compounds, people are random
combinations of invented first/last names, and e-mail addresses use the reserved ".example" TLD.
The job-change feed is simulated; no data provider is involved.

Outputs, per feed:
  data/<feed>/{accounts,contacts,prospects,competitors,events}.json   <- the agent may read these
  evals/keys/<feed>.json                                              <- answer key, agent never reads it

Feeds:
  dev   (seed 7)     used while building the agent and choosing thresholds
  eval  (seed 2026)  held out; acceptance results are measured on this feed only
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEED_START = dt.date(2026, 8, 1)
FEED_DAYS = 90

FIRST = ["Katherine", "Michael", "Alexander", "Elizabeth", "Christopher", "Jennifer", "Matthew", "Rebecca",
         "Nicholas", "Samantha", "Benjamin", "Jonathan", "Priya", "Marcus", "Elena", "Ravi", "Amara", "Diego",
         "Hannah", "Yusuf", "Mei", "Oliver", "Sofia", "Kwame", "Ingrid", "Mateo", "Leila", "Hiroshi", "Nadia",
         "Gabriel", "Fatima", "Lucas", "Chloe", "Andre", "Zainab", "Felix", "Marisol", "Dmitri", "Ayesha", "Theo",
         "Camila", "Anders", "Imani", "Rohan", "Beatrix", "Santiago", "Wanjiru", "Julian", "Anika", "Callum",
         "Lucia", "Malik", "Greta", "Idris", "Noor", "Emeka", "Sienna", "Viktor", "Tamsin", "Arjun"]
NICK = {"Katherine": "Kate", "Michael": "Mike", "Alexander": "Alex", "Elizabeth": "Liz", "Christopher": "Chris",
        "Jennifer": "Jen", "Matthew": "Matt", "Rebecca": "Becca", "Nicholas": "Nick", "Samantha": "Sam",
        "Benjamin": "Ben", "Jonathan": "Jon"}
LAST = ["Ramos", "Whitfield", "Okafor", "Lindqvist", "Mahlangu", "Castellano", "Brennan", "Oyelaran", "Takahashi",
        "Delacroix", "Petrov", "Nakamura", "Abernathy", "Kowalczyk", "Fairbanks", "Osei", "Vasquez", "Halvorsen",
        "Chaudhry", "Montgomery", "Zielinski", "Adeyemi", "Rosales", "Thorne", "Bergstrom", "Nguyen", "Patel",
        "Moreau", "Sandoval", "Eriksen", "Banerjee", "Calloway", "Dimitrov", "Escobar", "Fontaine", "Gallagher",
        "Hashemi", "Iyer", "Jankowski", "Kimura", "Laurent", "Marchetti", "Novak", "Ortega", "Prescott", "Quinlan",
        "Rutherford", "Sinclair", "Tran", "Underhill", "Varga", "Winslow", "Xiong", "Yamada", "Zimmerman",
        "Achterberg", "Bakshi", "Cardenas", "Dunmore", "Everhart", "Farouk", "Grayson", "Holloway", "Ibarra",
        "Jovanovic", "Kapoor", "Lombardi", "Mbeki", "Navarro", "Olsen", "Pereira", "Quist", "Reyes", "Sorensen",
        "Tanaka", "Uribe", "Voss", "Wadhwa", "Yilmaz", "Zhao", "Bellamy"]
CITIES = ["Austin", "Denver", "Seattle", "Toronto", "London", "Dublin", "Berlin", "Chicago", "Boston", "Atlanta",
          "Portland", "Singapore"]
PREFIXES = ["Lumen", "Brindle", "Quill", "Harbor", "Tamarack", "Nimbus", "Ferro", "Alder", "Cobalt", "Juniper",
            "Marlow", "Opal", "Pylon", "Sable", "Tessel", "Verity", "Wren", "Zephyr", "Granite", "Ember", "Cinder",
            "Delta", "Fable", "Gantry", "Hollis", "Ironwood", "Kestrel", "Lattice", "Mosaic", "Northwind",
            "Orchard", "Pinion", "Quartz", "Ridge", "Solace", "Thistle", "Umber", "Vantage", "Willow", "Yarrow",
            "Basalt", "Corvid", "Dunlin", "Estuary", "Fathom", "Glint", "Heron", "Isle", "Jasper", "Knoll"]
SUFFIXES = ["forge", "works", "loop", "grid", "stack", "labs", "base", "point", "scope", "flow", "path", "wave",
            "yard", "hub", "mint", "cast", "dock", "line", "port", "bridge"]
CHAMPION_TITLES = ["Product Manager", "Senior Product Manager", "Product Operations Lead", "Group Product Manager",
                   "Principal Product Manager"]
EXEC_TITLES = ["Head of Product", "VP Product", "Chief Product Officer"]
ADMIN_TITLES = ["Product Ops Analyst", "Workspace Admin", "IT Systems Analyst"]
POWER_TITLES = ["Associate Product Manager", "UX Researcher", "Customer Insights Analyst", "Product Designer"]
PLANS = [("Team", 9000, 0.45), ("Business", 18000, 0.40), ("Enterprise", 42000, 0.15)]
CSMS = ["Dana Whitlock", "Priscilla Odum", "Jorge Alvarenga", "Mina Takeda", "Brooks Hadley", "Ife Balogun",
        "Corinne Aubert", "Lars Nyberg"]
AMS = ["Hollis Grant", "Rupa Sethi", "Gideon Marsh", "Talia Brandt", "Omar Kessler", "Noelle Vance"]

SEPARATOR_TITLE_DRIFT = [("Senior ", "Sr "), ("Product Manager", "PM"), ("Product Operations", "Product Ops")]


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


class Generator:
    def __init__(self, seed: int):
        self.r = random.Random(seed)
        combos = [(p, s) for p in PREFIXES for s in SUFFIXES]
        self.r.shuffle(combos)
        self._combos = combos
        self.used_names: set[str] = set()

    # ---------------------------------------------------------------- companies
    def company(self) -> dict:
        p, s = self._combos.pop()
        return {"name": f"{p}{s}", "parts": [p, s]}

    # ---------------------------------------------------------------- variants
    def emp_variant(self, comp: dict, text_safe: bool) -> str:
        n = comp["name"]
        p, s = comp["parts"]
        pool = [n, n, n, f"{p} {s}", f"The {n}", n.lower()]
        pool += [f"{n} Inc"] if text_safe else [f"{n} Inc.", f"{n}, Inc.", n.upper()]
        return self.r.choice(pool)

    def title_variant(self, title: str, text_safe: bool) -> str:
        opts = [title, title]
        for a, b in SEPARATOR_TITLE_DRIFT:
            if a in title:
                opts.append(title.replace(a, b if text_safe else b))
        return self.r.choice(opts)

    # ---------------------------------------------------------------- people
    def person_name(self) -> tuple[str, str]:
        while True:
            f, l = self.r.choice(FIRST), self.r.choice(LAST)
            if f"{f} {l}" not in self.used_names:
                self.used_names.add(f"{f} {l}")
                return f, l

    def date_str(self, d: dt.date) -> str:
        return d.isoformat()

    # ---------------------------------------------------------------- build
    def build(self) -> tuple[dict, dict]:
        r = self.r
        competitors = []
        for i in range(5):
            c = self.company()
            competitors.append({"id": f"C{i + 1:02d}", "name": c["name"], "parts": c["parts"],
                                "domain": slug(c["name"]) + ".example"})
        accounts, contacts = [], []
        for i in range(300):
            c = self.company()
            roll, acc = r.random(), 0.0
            plan, base = PLANS[0][0], PLANS[0][1]
            for pn, pb, pw in PLANS:
                acc += pw
                if roll <= acc:
                    plan, base = pn, pb
                    break
            account = {
                "id": f"A{i + 1:04d}", "name": c["name"], "parts": c["parts"], "domain": slug(c["name"]) + ".example",
                "plan": plan, "arr": int(round(base * r.uniform(0.9, 1.15) / 500) * 500),
                "renewal_date": self.date_str(FEED_START + dt.timedelta(days=r.randint(10, 400))),
                "customer_since": self.date_str(FEED_START - dt.timedelta(days=r.randint(200, 1600))),
                "usage_level": r.choice(["low", "medium", "medium", "high", "high"]),
                "csm": r.choice(CSMS), "account_manager": r.choice(AMS),
            }
            accounts.append(account)
            roles = ["champion", "admin", "power_user", "power_user", "exec_sponsor"]
            if r.random() < 0.3:
                roles[2] = "champion"
            for role in roles:
                f, l = self.person_name()
                title = r.choice({"champion": CHAMPION_TITLES, "exec_sponsor": EXEC_TITLES,
                                  "admin": ADMIN_TITLES, "power_user": POWER_TITLES}[role])
                since = dt.date.fromisoformat(account["customer_since"]) + dt.timedelta(days=r.randint(0, 120))
                contacts.append({
                    "id": f"K{len(contacts) + 1:05d}", "account_id": account["id"], "first_name": f, "last_name": l,
                    "full_name": f"{f} {l}", "email": f"{f.lower()}.{l.lower()}@{account['domain']}",
                    "title": title, "city": r.choice(CITIES), "role": role,
                    "signup_date": self.date_str(since),
                    "last_active_date": self.date_str(FEED_START - dt.timedelta(days=r.randint(0, 30))),
                    "boards_created": r.randint(3, 60),
                })
        prospects = []
        for i in range(400):
            c = self.company()
            prospects.append({"id": f"P{i + 1:04d}", "name": c["name"], "parts": c["parts"],
                              "domain": slug(c["name"]) + ".example", "icp_fit": r.random() < 0.55,
                              "employees": r.choice([40, 80, 150, 300, 600, 1200]),
                              "industry": r.choice(["Fintech", "Devtools", "Healthtech", "Martech", "HR tech",
                                                    "Logistics software", "Security software"])})
        unknown = [self.company() for _ in range(6)]
        return self._events(accounts, contacts, prospects, competitors, unknown)

    # ---------------------------------------------------------------- events
    def _events(self, accounts, contacts, prospects, competitors, unknown):
        r = self.r
        acct = {a["id"]: a for a in accounts}
        watch = [c for c in contacts if c["role"] in ("champion", "exec_sponsor")]
        r.shuffle(watch)
        pool = iter(watch)
        fit = [p for p in prospects if p["icp_fit"]]
        nofit = [p for p in prospects if not p["icp_fit"]]
        plan = ([("moved_fit", 30), ("moved_customer", 6), ("moved_competitor", 5), ("moved_nofit", 6),
                 ("moved_unknown", 3), ("left", 5), ("title_change", 12), ("collision", 9)])
        specs = []
        for kind, n in plan:
            specs += [kind] * n
        r.shuffle(specs)
        # surname changes happen on 4 true moves
        move_idx = [i for i, k in enumerate(specs) if k.startswith("moved") or k == "left"]
        surname_change = set(r.sample(move_idx, 4))
        collision_levels = ["easy"] * 5 + ["medium"] * 2 + ["hard"] * 2
        r.shuffle(collision_levels)
        coll_i = 0
        days = sorted(r.randint(0, FEED_DAYS - 1) for _ in specs)
        base_events = []
        for idx, (kind, day) in enumerate(zip(specs, days)):
            received = FEED_START + dt.timedelta(days=day)
            fmt = "text" if r.random() < 0.30 else "structured"
            text_safe = fmt == "text"
            noise: list[str] = []
            contact = next(pool)
            account = acct[contact["account_id"]]
            key = {"type": kind, "received_at": received.isoformat(), "format": fmt, "noise": noise,
                   "contact_id": contact["id"], "account_id": account["id"]}
            first = contact["first_name"]
            last = contact["last_name"]
            payload = dict(full_name=None, prior_employer=None, prior_title=None, prior_email_domain=None,
                           new_employer=None, new_title=None, location=None)

            if kind == "collision":
                level = collision_levels[coll_i]
                coll_i += 1
                # a DIFFERENT person who happens to share the namesake's full name
                other = r.choice([c for c in accounts + prospects if c["id"] != account["id"]])
                payload["full_name"] = contact["full_name"]
                new_target = r.choice(fit)
                payload["new_employer"] = self.emp_variant(new_target, text_safe)
                payload["new_title"] = r.choice(CHAMPION_TITLES + POWER_TITLES)
                if level == "easy":
                    payload["prior_employer"] = self.emp_variant(other, text_safe)
                    payload["prior_title"] = r.choice(POWER_TITLES)
                    payload["location"] = r.choice([c for c in CITIES if c != contact["city"]])
                elif level == "medium":
                    payload["prior_employer"] = self.emp_variant(other, text_safe)
                    payload["prior_title"] = self.title_variant(contact["title"], text_safe)
                    payload["location"] = contact["city"]
                else:  # hard: sparse profile, same city, same title, no prior employer
                    payload["prior_title"] = contact["title"]
                    payload["location"] = contact["city"]
                noise.append(f"collision:{level}")
                key.update(true_person=None, namesake_contact_id=contact["id"], new_employer_id=new_target["id"],
                           collision_level=level)
                base_events.append((received, fmt, kind, payload, key))
                continue

            # ---- same person events
            used_first = first
            if first in NICK and r.random() < 0.4:
                used_first = NICK[first]
                noise.append("nickname")
            used_last = last
            if idx in surname_change:
                used_last = r.choice([l for l in LAST if l != last])
                noise.append("surname_change")
            payload["full_name"] = f"{used_first} {used_last}"
            if r.random() > 0.12:
                payload["prior_employer"] = self.emp_variant(account, text_safe)
            else:
                noise.append("prior_employer_missing")
            if r.random() > 0.15:
                payload["prior_title"] = self.title_variant(contact["title"], text_safe)
            else:
                noise.append("prior_title_missing")
            if not text_safe and r.random() < 0.55:
                payload["prior_email_domain"] = account["domain"]
            if r.random() < 0.70:
                payload["location"] = contact["city"]
            elif r.random() < 0.5:
                payload["location"] = r.choice([c for c in CITIES if c != contact["city"]])
                noise.append("city_changed")
            key["true_person"] = contact["id"]

            if kind == "title_change":
                payload["new_employer"] = payload["prior_employer"] or self.emp_variant(account, text_safe)
                payload["prior_employer"] = payload["prior_employer"] or payload["new_employer"]
                payload["new_title"] = r.choice([t for t in CHAMPION_TITLES + EXEC_TITLES if t != contact["title"]])
                key["new_employer_id"] = account["id"]
            elif kind == "left":
                if text_safe and payload["prior_employer"] is None:
                    payload["prior_employer"] = self.emp_variant(account, text_safe)
                    noise.remove("prior_employer_missing")
            else:
                if kind == "moved_fit":
                    tgt = r.choice(fit)
                elif kind == "moved_nofit":
                    tgt = r.choice(nofit)
                elif kind == "moved_competitor":
                    tgt = r.choice(competitors)
                elif kind == "moved_customer":
                    tgt = r.choice([a for a in accounts if a["id"] != account["id"]])
                else:
                    tgt = r.choice(unknown)
                    tgt = dict(tgt, id="UNKNOWN")
                payload["new_employer"] = self.emp_variant(tgt, text_safe)
                payload["new_title"] = r.choice(CHAMPION_TITLES + EXEC_TITLES + POWER_TITLES)
                key["new_employer_id"] = tgt["id"]
            base_events.append((received, fmt, kind, payload, key))

        # ---- duplicates of 4 earlier moved_fit events (same person, variant employer, later date)
        cands = [e for e in base_events if e[2] == "moved_fit"
                 and e[0] <= FEED_START + dt.timedelta(days=FEED_DAYS - 8)]
        originals = r.sample(cands, 4)
        dups = []
        for orig in originals:
            received = orig[0] + dt.timedelta(days=r.randint(1, 6))
            fmt = "structured" if orig[1] == "text" else "text"
            ts = fmt == "text"
            c = next(c for c in contacts if c["id"] == orig[4]["contact_id"])
            account = acct[c["account_id"]]
            tgt_id = orig[4]["new_employer_id"]
            tgt = next(p for p in prospects if p["id"] == tgt_id)
            payload = dict(full_name=c["full_name"], prior_employer=self.emp_variant(account, ts),
                           prior_title=c["title"], prior_email_domain=None if ts else account["domain"],
                           new_employer=self.emp_variant(tgt, ts), new_title=orig[3]["new_title"],
                           location=c["city"])
            key = {"type": "duplicate", "received_at": received.isoformat(), "format": fmt,
                   "noise": ["duplicate", "variant_employer_name", "shifted_date"], "contact_id": c["id"],
                   "account_id": account["id"], "true_person": c["id"], "new_employer_id": tgt_id,
                   "dup_of_index": base_events.index(orig)}
            dups.append((received, fmt, "duplicate", payload, key))

        allev = base_events + dups
        order = sorted(range(len(allev)), key=lambda i: (allev[i][0], i))
        new_id = {old: f"E{n + 1:03d}" for n, old in enumerate(order)}
        events, keys = [], {}
        for old in order:
            received, fmt, kind, payload, key = allev[old]
            eid = new_id[old]
            ev = {"event_id": eid, "received_at": received.isoformat(), "source": "simulated-feed", "format": fmt}
            if fmt == "structured":
                ev["structured"] = payload
            else:
                ev["text"] = self.render_text(payload, kind)
            events.append(ev)
            if "dup_of_index" in key:
                key["dup_of"] = new_id[key.pop("dup_of_index")]
            keys[eid] = key
        self._finish_keys(keys, acct, accounts, prospects, competitors)
        data = {"accounts": accounts, "contacts": contacts, "prospects": prospects, "competitors": competitors,
                "events": events}
        return data, {"events": keys}

    def render_text(self, p: dict, kind: str) -> str:
        name, new_emp, new_title = p["full_name"], p["new_employer"], p["new_title"]
        prior_emp, prior_title, loc = p["prior_employer"], p["prior_title"], p["location"]
        if kind == "left":
            s = f"{name} has left {prior_emp}"
            if prior_title:
                s += f", where they were {prior_title}"
            return s + ". No new role announced."
        if kind == "title_change":
            s = f"Congratulations to {name}, now {new_title} at {new_emp}"
            if prior_title:
                s += f" (formerly {prior_title})"
            return s + "."
        if self.r.random() < 0.5:
            s = f"{name} has joined {new_emp} as {new_title}."
            if prior_title and prior_emp:
                s += f" Previously {prior_title} at {prior_emp}."
            elif prior_title:
                s += f" Previously {prior_title}."
            if loc:
                s += f" Based in {loc}."
            return s
        s = f"Thrilled to share I'm starting a new chapter as {new_title} at {new_emp}!"
        if prior_emp:
            s += f" After a great run at {prior_emp}, onward."
        s += f" — {name}"
        if loc:
            s += f", {loc}"
        return s

    def _finish_keys(self, keys, acct, accounts, prospects, competitors):
        comp_ids = {c["id"] for c in competitors}
        fit_ids = {p["id"] for p in prospects if p["icp_fit"]}
        nofit_ids = {p["id"] for p in prospects if not p["icp_fit"]}
        acct_ids = {a["id"] for a in accounts}
        for eid, k in keys.items():
            t = k["type"]
            received = dt.date.fromisoformat(k["received_at"])
            a = acct[k["account_id"]]
            days = (dt.date.fromisoformat(a["renewal_date"]) - received).days
            real_departure = t in ("moved_fit", "moved_customer", "moved_competitor", "moved_nofit",
                                   "moved_unknown", "left")
            k["real_departure"] = real_departure
            k["days_until_renewal"] = days if real_departure else None
            handling = {
                "moved_fit": ("departure:fit_prospect", "draft_outreach", "risk_flag"),
                "moved_customer": ("departure:customer", "notify_account_manager", "risk_flag"),
                "moved_competitor": ("departure:competitor", "suppress_outreach", "risk_flag"),
                "moved_nofit": ("departure:nofit_prospect", "log_only", "risk_flag"),
                "moved_unknown": ("departure:unknown_company", "log_only", "risk_flag"),
                "left": ("departure:no_new_employer", "none", "risk_flag"),
                "title_change": ("same_company_title_change", "update_record", "none"),
                "collision": ("no_match", "none", "none"),
                "duplicate": ("duplicate", "none", "none"),
            }[t]
            k["expected_label"] = handling[0]
            k["acceptable_labels"] = [handling[0]] + (["identity_review"] if t == "collision" else [])
            k["expected_new_company_play"] = handling[1]
            k["expected_old_account_play"] = handling[2]
            if t == "moved_competitor":
                assert k["new_employer_id"] in comp_ids
            if t == "moved_fit":
                assert k["new_employer_id"] in fit_ids
            if t == "moved_nofit":
                assert k["new_employer_id"] in nofit_ids
            if t == "moved_customer":
                assert k["new_employer_id"] in acct_ids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", choices=["dev", "eval"], required=True)
    ap.add_argument("--seed", type=int)
    a = ap.parse_args()
    seed = a.seed if a.seed is not None else {"dev": 7, "eval": 2026}[a.feed]
    data, key = Generator(seed).build()
    out = ROOT / "data" / a.feed
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in data.items():
        (out / f"{name}.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    kdir = ROOT / "evals" / "keys"
    kdir.mkdir(parents=True, exist_ok=True)
    key["feed"], key["seed"] = a.feed, seed
    (kdir / f"{a.feed}.json").write_text(json.dumps(key, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    kinds: dict[str, int] = {}
    for k in key["events"].values():
        kinds[k["type"]] = kinds.get(k["type"], 0) + 1
    print(f"feed={a.feed} seed={seed} accounts={len(data['accounts'])} contacts={len(data['contacts'])} "
          f"prospects={len(data['prospects'])} competitors={len(data['competitors'])} events={len(data['events'])}")
    print(json.dumps(kinds, sort_keys=True))


if __name__ == "__main__":
    main()
