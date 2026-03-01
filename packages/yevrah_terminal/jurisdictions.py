"""
CourtListener Jurisdiction/Court Codes Reference
=================================================
Source: https://www.courtlistener.com/help/api/jurisdictions/

CourtListener has 3,353+ jurisdictions. This module provides:
1. Understanding the U.S. court system structure
2. Selecting appropriate courts for legal research queries
3. Using CourtListener API jurisdiction parameters

COURT SYSTEM BREAKDOWN:
-----------------------
Total courts: 2,805+
By System:
  - State: 2,323 courts
  - Federal: 407 courts
  - Tribal: 64 courts
  - International: 4 courts
  - Colonial/Historical: 2 courts

By Type:
  - Trial: 2,111 courts
  - Appellate: 360 courts
  - Special: 157 courts
  - Bankruptcy: 101 courts
  - Attorney General Opinions: 15 jurisdictions

PEDAGOGICAL NOTE FOR AI MODELS:
-------------------------------
When a user asks for case law research, you must determine:
1. Is this a FEDERAL or STATE law issue (or both)?
2. Which specific courts have relevant precedential authority?
3. What is the binding vs. persuasive authority hierarchy?

This guide explains WHEN and WHY to select specific courts, not just
what courts exist.
"""

# =============================================================================
# PART 1: UNDERSTANDING FEDERAL VS. STATE JURISDICTION
# =============================================================================

JURISDICTION_FUNDAMENTALS = """
FEDERAL VS. STATE: WHEN TO SEARCH WHICH SYSTEM
==============================================

SEARCH FEDERAL COURTS WHEN:
---------------------------
• Federal Question: Case involves U.S. Constitution, federal statutes, or treaties
  - Examples: Civil rights (§1983), antitrust, securities fraud, patent, copyright,
    bankruptcy, immigration, federal tax, ERISA, federal employment (Title VII)

• Exclusive Federal Jurisdiction (MUST be in federal court):
  - Patent and copyright infringement
  - Bankruptcy
  - Federal criminal prosecutions
  - Admiralty/maritime (generally)
  - Antitrust
  - Securities Exchange Act claims
  - IRS/federal tax disputes

• Diversity Jurisdiction: State law claims where:
  - Parties are from different states AND
  - Amount in controversy exceeds $75,000
  - NOTE: Federal court applies STATE substantive law in diversity cases

SEARCH STATE COURTS WHEN:
-------------------------
• State Law Issues: Most common law and state statutory claims
  - Contract disputes (non-federal)
  - Tort/personal injury/negligence
  - Property disputes
  - Family law (divorce, custody, adoption)
  - Probate/wills/estates
  - State criminal law
  - Workers' compensation
  - Most employment disputes (unless Title VII, ERISA, etc.)
  - State consumer protection
  - Insurance coverage disputes

SEARCH BOTH SYSTEMS WHEN:
-------------------------
• The legal issue could arise in either forum
• You want comprehensive research on how courts interpret similar issues
• State law claims that sometimes appear in federal court via diversity
• Constitutional issues that state courts also address

SEARCH TRIBAL COURTS WHEN:
--------------------------
• Disputes involving tribal members on tribal lands
• Matters governed by tribal law or custom
• Indian Child Welfare Act (ICWA) proceedings
• Contracts with tribal entities that specify tribal court jurisdiction
• Criminal matters involving tribal members (limited jurisdiction)

Note: Tribal courts have their own substantive and procedural law.
Major tribal court systems include Navajo Nation (largest), Hopi,
Mashantucket Pequot, and approximately 400 others nationwide.

SEARCH ATTORNEY GENERAL OPINIONS WHEN:
--------------------------------------
• Seeking official state legal interpretations (not binding but persuasive)
• Researching how a state agency interprets state law
• 15 states have AG opinions in CourtListener: AR, CA, CO, FL, KS, LA, MD,
  MO, NE, NY, OH, OK, TX, WA, WI

COMMON MISTAKE: Assuming all "important" cases are federal. Most litigation
occurs in state courts. Don't overlook state authority.
"""

# =============================================================================
# PART 2: PRECEDENTIAL AUTHORITY HIERARCHY
# =============================================================================

PRECEDENT_HIERARCHY = """
UNDERSTANDING BINDING VS. PERSUASIVE AUTHORITY
==============================================

FEDERAL SYSTEM HIERARCHY:
-------------------------
1. U.S. Supreme Court (scotus) - Binds ALL courts on federal questions
2. Circuit Courts of Appeals (ca1-ca11, cadc, cafc) - Bind district courts within circuit
3. District Courts - Trial level, not binding precedent

KEY INSIGHT: A 9th Circuit decision does NOT bind:
  - Other circuits (persuasive only)
  - State courts (persuasive only, even on federal questions)
  - District courts outside the 9th Circuit

GEOGRAPHIC CIRCUIT MAP:
  ca1:  ME, MA, NH, RI, PR
  ca2:  CT, NY, VT
  ca3:  DE, NJ, PA, VI
  ca4:  MD, NC, SC, VA, WV
  ca5:  LA, MS, TX
  ca6:  KY, MI, OH, TN
  ca7:  IL, IN, WI
  ca8:  AR, IA, MN, MO, NE, ND, SD
  ca9:  AK, AZ, CA, GU, HI, ID, MT, NV, NMI, OR, WA
  ca10: CO, KS, NM, OK, UT, WY
  ca11: AL, FL, GA
  cadc: District of Columbia
  cafc: Federal Circuit (patents, gov't contracts, etc. - nationwide)

STATE SYSTEM HIERARCHY:
-----------------------
1. State Supreme Court - Binds all courts in that state
2. Intermediate Appellate Court - Binds trial courts (may vary by district)
3. Trial Courts - Not binding precedent

KEY INSIGHT: State supreme court decisions on state law questions are
FINAL - even the U.S. Supreme Court cannot override a state court's
interpretation of its own state's constitution or statutes.

PRACTICAL RESEARCH STRATEGY:
----------------------------
For a Virginia premises liability case:
  PRIMARY (binding):    va (VA Supreme Court), vactapp (VA Court of Appeals)
  SECONDARY (persuasive): Other state courts with similar law
  USUALLY NOT RELEVANT: ca4 (4th Circuit) - federal courts rarely hear
                        premises liability unless diversity jurisdiction
"""

# =============================================================================
# PART 3: COURT CODE REFERENCE
# =============================================================================

# Federal Appellate Courts
FEDERAL_APPELLATE_COURTS = {
    "scotus": "Supreme Court of the United States",
    "ca1": "Court of Appeals for the First Circuit",
    "ca2": "Court of Appeals for the Second Circuit",
    "ca3": "Court of Appeals for the Third Circuit",
    "ca4": "Court of Appeals for the Fourth Circuit",
    "ca5": "Court of Appeals for the Fifth Circuit",
    "ca6": "Court of Appeals for the Sixth Circuit",
    "ca7": "Court of Appeals for the Seventh Circuit",
    "ca8": "Court of Appeals for the Eighth Circuit",
    "ca9": "Court of Appeals for the Ninth Circuit",
    "ca10": "Court of Appeals for the Tenth Circuit",
    "ca11": "Court of Appeals for the Eleventh Circuit",
    "cadc": "Court of Appeals for the D.C. Circuit",
    "cafc": "Court of Appeals for the Federal Circuit",
}

# Federal District Courts
FEDERAL_DISTRICT_COURTS = {
    # Alabama
    "almd": "Middle District of Alabama",
    "alnd": "Northern District of Alabama",
    "alsd": "Southern District of Alabama",
    # Alaska
    "akd": "District of Alaska",
    # Arizona
    "azd": "District of Arizona",
    # Arkansas
    "ared": "Eastern District of Arkansas",
    "arwd": "Western District of Arkansas",
    # California
    "cacd": "Central District of California",
    "caed": "Eastern District of California",
    "cand": "Northern District of California",
    "casd": "Southern District of California",
    # Colorado
    "cod": "District of Colorado",
    # Connecticut
    "ctd": "District of Connecticut",
    # Delaware
    "ded": "District of Delaware",
    # District of Columbia
    "dcd": "District of Columbia",
    # Florida
    "flmd": "Middle District of Florida",
    "flnd": "Northern District of Florida",
    "flsd": "Southern District of Florida",
    # Georgia
    "gamd": "Middle District of Georgia",
    "gand": "Northern District of Georgia",
    "gasd": "Southern District of Georgia",
    # Hawaii
    "hid": "District of Hawaii",
    # Idaho
    "idd": "District of Idaho",
    # Illinois
    "ilcd": "Central District of Illinois",
    "ilnd": "Northern District of Illinois",
    "ilsd": "Southern District of Illinois",
    # Indiana
    "innd": "Northern District of Indiana",
    "insd": "Southern District of Indiana",
    # Iowa
    "iand": "Northern District of Iowa",
    "iasd": "Southern District of Iowa",
    # Kansas
    "ksd": "District of Kansas",
    # Kentucky
    "kyed": "Eastern District of Kentucky",
    "kywd": "Western District of Kentucky",
    # Louisiana
    "laed": "Eastern District of Louisiana",
    "lamd": "Middle District of Louisiana",
    "lawd": "Western District of Louisiana",
    # Maine
    "med": "District of Maine",
    # Maryland
    "mdd": "District of Maryland",
    # Massachusetts
    "mad": "District of Massachusetts",
    # Michigan
    "mied": "Eastern District of Michigan",
    "miwd": "Western District of Michigan",
    # Minnesota
    "mnd": "District of Minnesota",
    # Mississippi
    "msnd": "Northern District of Mississippi",
    "mssd": "Southern District of Mississippi",
    # Missouri
    "moed": "Eastern District of Missouri",
    "mowd": "Western District of Missouri",
    # Montana
    "mtd": "District of Montana",
    # Nebraska
    "ned": "District of Nebraska",
    # Nevada
    "nvd": "District of Nevada",
    # New Hampshire
    "nhd": "District of New Hampshire",
    # New Jersey
    "njd": "District of New Jersey",
    # New Mexico
    "nmd": "District of New Mexico",
    # New York
    "nyed": "Eastern District of New York",
    "nynd": "Northern District of New York",
    "nysd": "Southern District of New York",
    "nywd": "Western District of New York",
    # North Carolina
    "nced": "Eastern District of North Carolina",
    "ncmd": "Middle District of North Carolina",
    "ncwd": "Western District of North Carolina",
    # North Dakota
    "ndd": "District of North Dakota",
    # Ohio
    "ohnd": "Northern District of Ohio",
    "ohsd": "Southern District of Ohio",
    # Oklahoma
    "oked": "Eastern District of Oklahoma",
    "oknd": "Northern District of Oklahoma",
    "okwd": "Western District of Oklahoma",
    # Oregon
    "ord": "District of Oregon",
    # Pennsylvania
    "paed": "Eastern District of Pennsylvania",
    "pamd": "Middle District of Pennsylvania",
    "pawd": "Western District of Pennsylvania",
    # Rhode Island
    "rid": "District of Rhode Island",
    # South Carolina
    "scd": "District of South Carolina",
    # South Dakota
    "sdd": "District of South Dakota",
    # Tennessee
    "tned": "Eastern District of Tennessee",
    "tnmd": "Middle District of Tennessee",
    "tnwd": "Western District of Tennessee",
    # Texas
    "txed": "Eastern District of Texas",
    "txnd": "Northern District of Texas",
    "txsd": "Southern District of Texas",
    "txwd": "Western District of Texas",
    # Utah
    "utd": "District of Utah",
    # Vermont
    "vtd": "District of Vermont",
    # Virginia
    "vaed": "Eastern District of Virginia",
    "vawd": "Western District of Virginia",
    # Washington
    "waed": "Eastern District of Washington",
    "wawd": "Western District of Washington",
    # West Virginia
    "wvnd": "Northern District of West Virginia",
    "wvsd": "Southern District of West Virginia",
    # Wisconsin
    "wied": "Eastern District of Wisconsin",
    "wiwd": "Western District of Wisconsin",
    # Wyoming
    "wyd": "District of Wyoming",
    # Territories
    "gud": "District of Guam",
    "nmid": "District of the Northern Mariana Islands",
    "prd": "District of Puerto Rico",
    "vid": "District of the Virgin Islands",
}

# State Supreme Courts
STATE_SUPREME_COURTS = {
    "ala": "Supreme Court of Alabama",
    "alaska": "Supreme Court of Alaska",
    "ariz": "Supreme Court of Arizona",
    "ark": "Supreme Court of Arkansas",
    "cal": "Supreme Court of California",
    "colo": "Supreme Court of Colorado",
    "conn": "Supreme Court of Connecticut",
    "del": "Supreme Court of Delaware",
    "fla": "Supreme Court of Florida",
    "ga": "Supreme Court of Georgia",
    "haw": "Supreme Court of Hawaii",
    "idaho": "Supreme Court of Idaho",
    "ill": "Supreme Court of Illinois",
    "ind": "Supreme Court of Indiana",
    "iowa": "Supreme Court of Iowa",
    "kan": "Supreme Court of Kansas",
    "ky": "Supreme Court of Kentucky",
    "la": "Supreme Court of Louisiana",
    "me": "Supreme Judicial Court of Maine",
    "md": "Court of Appeals of Maryland",  # NOTE: Highest court despite name
    "mass": "Supreme Judicial Court of Massachusetts",
    "mich": "Supreme Court of Michigan",
    "minn": "Supreme Court of Minnesota",
    "miss": "Supreme Court of Mississippi",
    "mo": "Supreme Court of Missouri",
    "mont": "Supreme Court of Montana",
    "neb": "Supreme Court of Nebraska",
    "nev": "Supreme Court of Nevada",
    "nh": "Supreme Court of New Hampshire",
    "nj": "Supreme Court of New Jersey",
    "nm": "Supreme Court of New Mexico",
    "ny": "Court of Appeals of New York",  # NOTE: Highest court despite name
    "nc": "Supreme Court of North Carolina",
    "nd": "Supreme Court of North Dakota",
    "ohio": "Supreme Court of Ohio",
    "okla": "Supreme Court of Oklahoma",
    "or": "Supreme Court of Oregon",
    "pa": "Supreme Court of Pennsylvania",
    "ri": "Supreme Court of Rhode Island",
    "sc": "Supreme Court of South Carolina",
    "sd": "Supreme Court of South Dakota",
    "tenn": "Supreme Court of Tennessee",
    "tex": "Supreme Court of Texas",  # Civil cases only
    "texcrimapp": "Texas Court of Criminal Appeals",  # Criminal cases - also highest court
    "utah": "Supreme Court of Utah",
    "vt": "Supreme Court of Vermont",
    "va": "Supreme Court of Virginia",
    "wash": "Supreme Court of Washington",
    "wva": "Supreme Court of Appeals of West Virginia",
    "wis": "Supreme Court of Wisconsin",
    "wyo": "Supreme Court of Wyoming",
    "dc": "District of Columbia Court of Appeals",  # Highest DC court
}

# State Intermediate Appellate Courts
STATE_APPELLATE_COURTS = {
    "alactapp": "Court of Civil Appeals of Alabama",
    "alacrimapp": "Court of Criminal Appeals of Alabama",
    "alaskactapp": "Court of Appeals of Alaska",
    "arizctapp": "Court of Appeals of Arizona",
    "arkctapp": "Court of Appeals of Arkansas",
    "calctapp": "California Court of Appeal",
    "coloctapp": "Colorado Court of Appeals",
    "connappct": "Appellate Court of Connecticut",
    "flactapp": "Florida District Courts of Appeal",
    "gactapp": "Court of Appeals of Georgia",
    "hawctapp": "Intermediate Court of Appeals of Hawaii",
    "idahoctapp": "Court of Appeals of Idaho",
    "illappct": "Appellate Court of Illinois",
    "indctapp": "Court of Appeals of Indiana",
    "iowactapp": "Court of Appeals of Iowa",
    "kanctapp": "Court of Appeals of Kansas",
    "kyctapp": "Court of Appeals of Kentucky",
    "lactapp": "Louisiana Courts of Appeal",
    "mdctspecapp": "Court of Special Appeals of Maryland",  # Intermediate (despite "Special")
    "massappct": "Appeals Court of Massachusetts",
    "michctapp": "Court of Appeals of Michigan",
    "minnctapp": "Court of Appeals of Minnesota",
    "missctapp": "Court of Appeals of Mississippi",
    "moctapp": "Missouri Court of Appeals",
    "nebctapp": "Nebraska Court of Appeals",
    "nevapp": "Nevada Court of Appeals",
    "njsuperctappdiv": "Superior Court of New Jersey, Appellate Division",
    "nmctapp": "Court of Appeals of New Mexico",
    "nyappdiv": "New York Supreme Court, Appellate Division",
    "nyappterm": "New York Supreme Court, Appellate Term",
    "ncctapp": "Court of Appeals of North Carolina",
    "ndctapp": "Court of Appeals of North Dakota",
    "ohioctapp": "Ohio Court of Appeals",
    "oklacivapp": "Court of Civil Appeals of Oklahoma",
    "oklacrimapp": "Court of Criminal Appeals of Oklahoma",
    "orctapp": "Court of Appeals of Oregon",
    "pasuperct": "Superior Court of Pennsylvania",
    "pacommwct": "Commonwealth Court of Pennsylvania",
    "scctapp": "Court of Appeals of South Carolina",
    "tennctapp": "Court of Appeals of Tennessee",
    "tenncrimapp": "Court of Criminal Appeals of Tennessee",
    "texapp": "Texas Courts of Appeals",  # Intermediate - NOT same as texcrimapp
    "utahctapp": "Court of Appeals of Utah",
    "vactapp": "Court of Appeals of Virginia",
    "washctapp": "Washington Court of Appeals",
    "wisctapp": "Wisconsin Court of Appeals",
}

# Specialty Federal Courts
SPECIALTY_COURTS = {
    "armfor": "United States Court of Appeals for the Armed Forces",
    "afcca": "Air Force Court of Criminal Appeals",
    "asbca": "Armed Services Board of Contract Appeals",
    "bva": "Board of Veterans' Appeals",
    "uscfc": "United States Court of Federal Claims",
    "tax": "United States Tax Court",
    "cit": "United States Court of International Trade",
    "bap1": "Bankruptcy Appellate Panel of the First Circuit",
    "bap2": "Bankruptcy Appellate Panel of the Second Circuit",
    "bap6": "Bankruptcy Appellate Panel of the Sixth Circuit",
    "bap8": "Bankruptcy Appellate Panel of the Eighth Circuit",
    "bap9": "Bankruptcy Appellate Panel of the Ninth Circuit",
    "bap10": "Bankruptcy Appellate Panel of the Tenth Circuit",
}

# Federal Bankruptcy Courts (101 courts - pattern: [state][district]b)
FEDERAL_BANKRUPTCY_COURTS = {
    # Sample - full list uses pattern [state abbrev][district]b
    # Alabama
    "almb": "Bankruptcy Court, M.D. Alabama",
    "alnb": "Bankruptcy Court, N.D. Alabama",
    "alsb": "Bankruptcy Court, S.D. Alabama",
    # California
    "cacb": "Bankruptcy Court, C.D. California",
    "caeb": "Bankruptcy Court, E.D. California",
    "canb": "Bankruptcy Court, N.D. California",
    "casb": "Bankruptcy Court, S.D. California",
    # New York
    "nyeb": "Bankruptcy Court, E.D. New York",
    "nynb": "Bankruptcy Court, N.D. New York",
    "nysb": "Bankruptcy Court, S.D. New York",
    "nywb": "Bankruptcy Court, W.D. New York",
    # Texas
    "txeb": "Bankruptcy Court, E.D. Texas",
    "txnb": "Bankruptcy Court, N.D. Texas",
    "txsb": "Bankruptcy Court, S.D. Texas",
    "txwb": "Bankruptcy Court, W.D. Texas",
    # Pattern note for all others
    "_pattern": "Use [state][district]b format (e.g., 'flsb' for S.D. Florida Bankruptcy)",
}

# Military Courts
MILITARY_COURTS = {
    "armfor": "United States Court of Appeals for the Armed Forces",
    "afcca": "U.S. Air Force Court of Criminal Appeals",
    "acca": "U.S. Army Court of Criminal Appeals",
    "nmcca": "U.S. Navy-Marine Corps Court of Criminal Appeals",
    "uscgcoca": "U.S. Coast Guard Court of Criminal Appeals",
    "cma": "United States Court of Military Appeals (historical)",
    "mc": "United States Court of Military Commission Review",
}

# Historical Courts (still searchable for older cases)
HISTORICAL_COURTS = {
    "ccpa": "Court of Customs and Patent Appeals (predecessor to CAFC, abolished 1982)",
    "cc": "Court of Claims (predecessor to Fed Claims, abolished 1982)",
    "cusc": "Customs Court (predecessor to CIT, abolished 1980)",
    "eca": "Emergency Court of Appeals",
    "tecoa": "Temporary Emergency Court of Appeals",
    "bta": "United States Board of Tax Appeals (predecessor to Tax Court)",
    # Historical Circuit Courts (pre-1912)
    "uscirct": "United States Circuit Courts (abolished 1912)",
}

# Attorney General Opinions (15 states have AG opinions in CourtListener)
ATTORNEY_GENERAL_OPINIONS = {
    "arkag": "Arkansas Attorney General Reports",
    "calag": "California Attorney General Reports",
    "coloag": "Colorado Attorney General Reports",
    "flaag": "Florida Attorney General Reports",
    "kanag": "Kansas Attorney General Reports",
    "laag": "Louisiana Attorney General Reports",
    "mdag": "Maryland Attorney General Reports",
    "moag": "Missouri Attorney General Reports",
    "nebag": "Nebraska Attorney General Reports",
    "nyag": "New York Attorney General Reports",
    "ohioag": "Opinion of The Ohio Attorney General",
    "oklaag": "Oklahoma Attorney General Reports",
    "texag": "Texas Attorney General Reports",
    "washag": "Washington Attorney General Reports",
    "wisag": "Wisconsin Attorney General Reports",
}

# Tribal Courts (64 tribal courts in CourtListener)
TRIBAL_COURTS = {
    # Navajo Nation (largest tribal court system)
    "navajo": "Navajo Nation Supreme Court",
    "navajoctapp": "Navajo Court of Appeals",
    "navajodistct": "Navajo Nation District Court",
    "navajofamct": "Navajo Nation Family Court",
    "navajochildct": "Navajo Nation Children's Court",
    # Hopi
    "hopiappct": "Hopi Appellate Court",
    "hopitr": "Hopi Trial Court",
    # Fort McDowell
    "ftmcdowell": "Fort McDowell Supreme Court",
    "ftmcdowctapp": "Fort McDowell Yavapai Nation Tribal Court of Appeals",
    "ftmcdowct": "Fort McDowell Yavapai Nation Tribal Court",
    # Mashantucket Pequot
    "pequotctapp": "Mashantucket Pequot Court of Appeals",
    "pequotct": "Mashantucket Pequot Tribal Court",
    # Mohegan
    "moheganctapp": "Mohegan Tribal Court of Appeals",
    "moheganct": "Mohegan Trial Court",
    # Others (sample - 64 total in courts-db)
    "chitctapp": "Chitimacha Court of Appeals",
    "coushct": "Coushatta Tribal Court",
    "tunicabct": "Tunica-Biloxi Tribal Court",
    "passamactapp": "Passamaquoddy Appellate Court",
    "grtravbandctapp": "Grand Traverse Band of Ottawa & Chippewa Indians Tribal Appellate Court",
}

# Combined dictionaries for easy lookup
ALL_COURTS = {
    **FEDERAL_APPELLATE_COURTS,
    **FEDERAL_DISTRICT_COURTS,
    **STATE_SUPREME_COURTS,
    **STATE_APPELLATE_COURTS,
    **SPECIALTY_COURTS,
    **FEDERAL_BANKRUPTCY_COURTS,
    **MILITARY_COURTS,
    **HISTORICAL_COURTS,
    **ATTORNEY_GENERAL_OPINIONS,
    **TRIBAL_COURTS,
}

# Convenience groupings for common query patterns
ALL_FEDERAL_APPELLATE = " ".join(FEDERAL_APPELLATE_COURTS.keys())
ALL_STATE_SUPREME = " ".join(STATE_SUPREME_COURTS.keys())
ALL_BAP = "bap1 bap2 bap6 bap8 bap9 bap10"
ALL_TRIBAL_APPELLATE = "navajo navajoctapp hopiappct pequotctapp moheganctapp"

# Popular/Common jurisdictions for quick selection
POPULAR_JURISDICTIONS = {
    "Federal Appeals": {
        "scotus": "Supreme Court of the United States",
        "ca9": "Ninth Circuit (CA, AZ, NV, OR, WA, etc.)",
        "ca2": "Second Circuit (NY, CT, VT)",
        "ca5": "Fifth Circuit (TX, LA, MS)",
        "ca11": "Eleventh Circuit (FL, GA, AL)",
        "cadc": "D.C. Circuit",
    },
    "California": {
        "cal": "California Supreme Court",
        "calctapp": "California Court of Appeal",
        "cand": "N.D. California (San Francisco)",
        "cacd": "C.D. California (Los Angeles)",
        "casd": "S.D. California (San Diego)",
        "caed": "E.D. California (Sacramento)",
    },
    "New York": {
        "ny": "New York Court of Appeals",
        "nyappdiv": "NY Appellate Division",
        "nysd": "S.D. New York (Manhattan)",
        "nyed": "E.D. New York (Brooklyn)",
    },
    "Texas": {
        "tex": "Texas Supreme Court",
        "texcrimapp": "Texas Court of Criminal Appeals",
        "texapp": "Texas Courts of Appeals",
        "txnd": "N.D. Texas (Dallas)",
        "txsd": "S.D. Texas (Houston)",
    },
    "Florida": {
        "fla": "Florida Supreme Court",
        "flactapp": "Florida District Courts of Appeal",
        "flsd": "S.D. Florida (Miami)",
        "flmd": "M.D. Florida (Orlando, Tampa)",
    },
}


def get_court_name(court_code: str) -> str:
    """Get the human-readable court name from a court code."""
    return ALL_COURTS.get(court_code, f"Unknown court: {court_code}")


def search_courts(query: str) -> dict:
    """
    Search for courts matching a query string.

    Args:
        query: Search string (partial match on code or name)

    Returns:
        Dictionary of matching {code: name} pairs
    """
    query_lower = query.lower()
    matches = {}
    for code, name in ALL_COURTS.items():
        if query_lower in code.lower() or query_lower in name.lower():
            matches[code] = name
    return matches


def get_bankruptcy_court(state: str, district: str = "") -> str:
    """
    Generate bankruptcy court code for a state/district.

    Args:
        state: Two-letter state abbreviation (e.g., 'CA', 'NY')
        district: District indicator: 'n', 's', 'e', 'w', 'm', 'c', or '' for single-district states

    Returns:
        Bankruptcy court code (e.g., 'canb' for N.D. California Bankruptcy)

    Examples:
        get_bankruptcy_court('CA', 'n')  → 'canb'
        get_bankruptcy_court('NY', 's')  → 'nysb'
        get_bankruptcy_court('AK')       → 'akb'
    """
    state = state.lower()
    district = district.lower()
    return f"{state}{district}b"


def get_state_courts(state_abbrev: str) -> dict:
    """
    Get all courts for a given state (both state and federal).

    Args:
        state_abbrev: Two-letter state abbreviation (e.g., 'CA', 'TX', 'NY')

    Returns:
        Dictionary with 'state' and 'federal' court groupings
    """
    state_abbrev = state_abbrev.lower()

    # Map state abbreviations to court code patterns
    state_patterns = {
        'al': {'supreme': 'ala', 'appellate': ['alactapp', 'alacrimapp'], 'federal': ['almd', 'alnd', 'alsd'], 'circuit': 'ca11'},
        'ak': {'supreme': 'alaska', 'appellate': ['alaskactapp'], 'federal': ['akd'], 'circuit': 'ca9'},
        'az': {'supreme': 'ariz', 'appellate': ['arizctapp'], 'federal': ['azd'], 'circuit': 'ca9'},
        'ar': {'supreme': 'ark', 'appellate': ['arkctapp'], 'federal': ['ared', 'arwd'], 'circuit': 'ca8'},
        'ca': {'supreme': 'cal', 'appellate': ['calctapp'], 'federal': ['cacd', 'caed', 'cand', 'casd'], 'circuit': 'ca9'},
        'co': {'supreme': 'colo', 'appellate': ['coloctapp'], 'federal': ['cod'], 'circuit': 'ca10'},
        'ct': {'supreme': 'conn', 'appellate': ['connappct'], 'federal': ['ctd'], 'circuit': 'ca2'},
        'de': {'supreme': 'del', 'appellate': [], 'federal': ['ded'], 'circuit': 'ca3'},
        'fl': {'supreme': 'fla', 'appellate': ['flactapp'], 'federal': ['flmd', 'flnd', 'flsd'], 'circuit': 'ca11'},
        'ga': {'supreme': 'ga', 'appellate': ['gactapp'], 'federal': ['gamd', 'gand', 'gasd'], 'circuit': 'ca11'},
        'hi': {'supreme': 'haw', 'appellate': ['hawctapp'], 'federal': ['hid'], 'circuit': 'ca9'},
        'id': {'supreme': 'idaho', 'appellate': ['idahoctapp'], 'federal': ['idd'], 'circuit': 'ca9'},
        'il': {'supreme': 'ill', 'appellate': ['illappct'], 'federal': ['ilcd', 'ilnd', 'ilsd'], 'circuit': 'ca7'},
        'in': {'supreme': 'ind', 'appellate': ['indctapp'], 'federal': ['innd', 'insd'], 'circuit': 'ca7'},
        'ia': {'supreme': 'iowa', 'appellate': ['iowactapp'], 'federal': ['iand', 'iasd'], 'circuit': 'ca8'},
        'ks': {'supreme': 'kan', 'appellate': ['kanctapp'], 'federal': ['ksd'], 'circuit': 'ca10'},
        'ky': {'supreme': 'ky', 'appellate': ['kyctapp'], 'federal': ['kyed', 'kywd'], 'circuit': 'ca6'},
        'la': {'supreme': 'la', 'appellate': ['lactapp'], 'federal': ['laed', 'lamd', 'lawd'], 'circuit': 'ca5'},
        'me': {'supreme': 'me', 'appellate': [], 'federal': ['med'], 'circuit': 'ca1'},
        'md': {'supreme': 'md', 'appellate': ['mdctspecapp'], 'federal': ['mdd'], 'circuit': 'ca4'},
        'ma': {'supreme': 'mass', 'appellate': ['massappct'], 'federal': ['mad'], 'circuit': 'ca1'},
        'mi': {'supreme': 'mich', 'appellate': ['michctapp'], 'federal': ['mied', 'miwd'], 'circuit': 'ca6'},
        'mn': {'supreme': 'minn', 'appellate': ['minnctapp'], 'federal': ['mnd'], 'circuit': 'ca8'},
        'ms': {'supreme': 'miss', 'appellate': ['missctapp'], 'federal': ['msnd', 'mssd'], 'circuit': 'ca5'},
        'mo': {'supreme': 'mo', 'appellate': ['moctapp'], 'federal': ['moed', 'mowd'], 'circuit': 'ca8'},
        'mt': {'supreme': 'mont', 'appellate': [], 'federal': ['mtd'], 'circuit': 'ca9'},
        'ne': {'supreme': 'neb', 'appellate': ['nebctapp'], 'federal': ['ned'], 'circuit': 'ca8'},
        'nv': {'supreme': 'nev', 'appellate': ['nevapp'], 'federal': ['nvd'], 'circuit': 'ca9'},
        'nh': {'supreme': 'nh', 'appellate': [], 'federal': ['nhd'], 'circuit': 'ca1'},
        'nj': {'supreme': 'nj', 'appellate': ['njsuperctappdiv'], 'federal': ['njd'], 'circuit': 'ca3'},
        'nm': {'supreme': 'nm', 'appellate': ['nmctapp'], 'federal': ['nmd'], 'circuit': 'ca10'},
        'ny': {'supreme': 'ny', 'appellate': ['nyappdiv', 'nyappterm'], 'federal': ['nyed', 'nynd', 'nysd', 'nywd'], 'circuit': 'ca2'},
        'nc': {'supreme': 'nc', 'appellate': ['ncctapp'], 'federal': ['nced', 'ncmd', 'ncwd'], 'circuit': 'ca4'},
        'nd': {'supreme': 'nd', 'appellate': ['ndctapp'], 'federal': ['ndd'], 'circuit': 'ca8'},
        'oh': {'supreme': 'ohio', 'appellate': ['ohioctapp'], 'federal': ['ohnd', 'ohsd'], 'circuit': 'ca6'},
        'ok': {'supreme': 'okla', 'appellate': ['oklacivapp', 'oklacrimapp'], 'federal': ['oked', 'oknd', 'okwd'], 'circuit': 'ca10'},
        'or': {'supreme': 'or', 'appellate': ['orctapp'], 'federal': ['ord'], 'circuit': 'ca9'},
        'pa': {'supreme': 'pa', 'appellate': ['pasuperct', 'pacommwct'], 'federal': ['paed', 'pamd', 'pawd'], 'circuit': 'ca3'},
        'ri': {'supreme': 'ri', 'appellate': [], 'federal': ['rid'], 'circuit': 'ca1'},
        'sc': {'supreme': 'sc', 'appellate': ['scctapp'], 'federal': ['scd'], 'circuit': 'ca4'},
        'sd': {'supreme': 'sd', 'appellate': [], 'federal': ['sdd'], 'circuit': 'ca8'},
        'tn': {'supreme': 'tenn', 'appellate': ['tennctapp', 'tenncrimapp'], 'federal': ['tned', 'tnmd', 'tnwd'], 'circuit': 'ca6'},
        'tx': {'supreme': 'tex', 'criminal': 'texcrimapp', 'appellate': ['texapp'], 'federal': ['txed', 'txnd', 'txsd', 'txwd'], 'circuit': 'ca5'},
        'ut': {'supreme': 'utah', 'appellate': ['utahctapp'], 'federal': ['utd'], 'circuit': 'ca10'},
        'vt': {'supreme': 'vt', 'appellate': [], 'federal': ['vtd'], 'circuit': 'ca2'},
        'va': {'supreme': 'va', 'appellate': ['vactapp'], 'federal': ['vaed', 'vawd'], 'circuit': 'ca4'},
        'wa': {'supreme': 'wash', 'appellate': ['washctapp'], 'federal': ['waed', 'wawd'], 'circuit': 'ca9'},
        'wv': {'supreme': 'wva', 'appellate': [], 'federal': ['wvnd', 'wvsd'], 'circuit': 'ca4'},
        'wi': {'supreme': 'wis', 'appellate': ['wisctapp'], 'federal': ['wied', 'wiwd'], 'circuit': 'ca7'},
        'wy': {'supreme': 'wyo', 'appellate': [], 'federal': ['wyd'], 'circuit': 'ca10'},
        'dc': {'supreme': 'dc', 'appellate': [], 'federal': ['dcd'], 'circuit': 'cadc'},
    }

    if state_abbrev not in state_patterns:
        return {"error": f"Unknown state: {state_abbrev}"}

    return state_patterns[state_abbrev]


def format_popular_jurisdictions() -> str:
    """Format popular jurisdictions for display."""
    lines = []
    for category, courts in POPULAR_JURISDICTIONS.items():
        lines.append(f"\n  {category}:")
        for code, name in courts.items():
            lines.append(f"    • {code} - {name}")
    return "\n".join(lines)


