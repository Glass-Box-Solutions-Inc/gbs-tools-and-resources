"""
California Workers' Compensation constants — venues, body parts, carriers,
specialties, employers, judges, ICD-10/CPT codes, medications.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

# WCAB District Offices (25 California venues)
WCAB_VENUES = [
    "Anaheim", "Bakersfield", "Eureka", "Fresno", "Goleta",
    "Grover Beach", "Inland Empire (Riverside)", "Long Beach",
    "Los Angeles", "Marina del Rey", "Oakland", "Oxnard",
    "Pomona", "Redding", "Sacramento", "Salinas",
    "San Bernardino", "San Diego", "San Francisco",
    "San Jose", "San Luis Obispo", "Santa Ana", "Santa Rosa",
    "Stockton", "Van Nuys",
]

# Body parts (DWC-coded categories)
BODY_PARTS = {
    "spine": [
        "cervical spine", "thoracic spine", "lumbar spine",
        "sacrum/coccyx",
    ],
    "upper_extremity": [
        "right shoulder", "left shoulder", "right elbow", "left elbow",
        "right wrist", "left wrist", "right hand", "left hand",
    ],
    "lower_extremity": [
        "right hip", "left hip", "right knee", "left knee",
        "right ankle", "left ankle", "right foot", "left foot",
    ],
    "internal": [
        "lungs", "heart", "kidneys", "liver", "gastrointestinal",
        "hearing (bilateral)", "vision (bilateral)",
    ],
    "psyche": [
        "psyche (anxiety)", "psyche (depression)", "psyche (PTSD)",
        "psyche (sleep disorder)",
    ],
    "head": [
        "head/brain (TBI)", "jaw/TMJ", "face",
    ],
}

ALL_BODY_PARTS = [bp for group in BODY_PARTS.values() for bp in group]

# Insurance carriers common in CA WC
INSURANCE_CARRIERS = [
    "State Compensation Insurance Fund (SCIF)",
    "Zenith Insurance Company",
    "Republic Indemnity",
    "ICW Group",
    "Gallagher Bassett Services",
    "Applied Underwriters",
    "Employers Holdings",
    "EMPLOYERS",
    "AmTrust Financial Services",
    "Kinsale Insurance Company",
    "Hartford Financial Services",
    "Travelers Insurance",
    "Liberty Mutual",
    "Sedgwick Claims Management",
    "Broadspire Services",
]

# Defense law firms
DEFENSE_FIRMS = [
    "Mitchell & Associates",
    "Bradford & Barthel LLP",
    "Laughlin, Falbo, Levy & Moresi LLP",
    "Shaw, Jacobsmeyer, Crain & Claffey",
    "Adelson, Testan, Brundo, Novell & Jimenez",
    "Hanna, Brophy, MacLean, McAleer & Jensen LLP",
    "LaFollette, Johnson, DeHaas, Fesler & Ames",
    "Manning & Kass, Ellrod, Ramirez, Trester LLP",
    "Pollak, Vida & Barer LLP",
    "Downs, Ward, Bender & Dantonio",
]

# Medical specialties
SPECIALTIES = [
    "Orthopedic Surgery",
    "Pain Management",
    "Neurology",
    "Physical Medicine & Rehabilitation (PM&R)",
    "Psychiatry",
    "Chiropractic",
    "Physical Therapy",
    "Internal Medicine",
    "Neurosurgery",
    "Hand Surgery",
]

# Employer templates by industry
EMPLOYER_TEMPLATES = {
    "government": [
        ("City of Los Angeles", "Public Works Maintenance Worker"),
        ("County of San Bernardino", "Sheriff's Deputy"),
        ("State of California — Caltrans", "Highway Maintenance Worker"),
        ("City of San Diego", "Firefighter/Paramedic"),
        ("County of Sacramento", "Correctional Officer"),
        ("City of Fresno", "Sanitation Worker"),
    ],
    "manufacturing": [
        ("Pacific Steel Fabrication Inc.", "Welder"),
        ("Golden State Packaging Co.", "Machine Operator"),
        ("West Coast Assembly Corp.", "Assembly Line Worker"),
        ("Sierra Nevada Lumber Mill", "Mill Worker"),
    ],
    "construction": [
        ("Turner Construction Company", "Carpenter"),
        ("Webcor Builders", "Ironworker"),
        ("Swinerton Incorporated", "Electrician"),
        ("DPR Construction", "Laborer"),
    ],
    "healthcare": [
        ("Kaiser Permanente", "Registered Nurse"),
        ("Dignity Health", "Certified Nursing Assistant"),
        ("Sutter Health", "Patient Care Technician"),
        ("UCLA Health", "Medical Assistant"),
    ],
    "warehouse_logistics": [
        ("Amazon Fulfillment Center ONT8", "Warehouse Associate"),
        ("FedEx Ground", "Package Handler"),
        ("UPS Supply Chain Solutions", "Forklift Operator"),
    ],
    "retail_service": [
        ("Safeway Inc.", "Grocery Stocker"),
        ("Home Depot", "Sales Associate"),
        ("Costco Wholesale", "Receiving Clerk"),
    ],
}

ALL_EMPLOYERS = [
    (industry, company, position)
    for industry, entries in EMPLOYER_TEMPLATES.items()
    for company, position in entries
]

# Judge names (fictional but realistic CA names)
JUDGE_NAMES = [
    "Hon. Patricia M. Torres",
    "Hon. Robert K. Nakamura",
    "Hon. Sarah J. Chen",
    "Hon. Michael A. Rodriguez",
    "Hon. Linda S. Washington",
    "Hon. James T. O'Brien",
    "Hon. Maria L. Gonzalez",
    "Hon. David W. Park",
    "Hon. Christine R. Patel",
    "Hon. Thomas E. Murphy",
    "Hon. Angela D. Kim",
    "Hon. Richard H. Vasquez",
    "Hon. Karen M. Yamamoto",
    "Hon. Steven P. Garcia",
    "Hon. Diane F. Johnson",
]

# Medical facility templates
MEDICAL_FACILITIES = [
    "Pacific Orthopedic & Spine Center",
    "Southern California Pain Institute",
    "Bay Area Neurology Associates",
    "Central Valley Medical Group",
    "Golden Gate Rehabilitation Center",
    "SoCal Sports Medicine & Orthopedics",
    "Valley Diagnostic Imaging Center",
    "Coast Chiropractic & Wellness",
    "Capitol Physical Therapy Associates",
    "Sierra Neurosurgical Institute",
    "Harbor Pain Management Clinic",
    "Inland Empire Orthopedic Specialists",
]

# Common ICD-10 codes for WC
ICD10_CODES = {
    "cervical spine": [("M54.2", "Cervicalgia"), ("M50.12", "Cervical disc disorder with radiculopathy")],
    "thoracic spine": [("M54.6", "Pain in thoracic spine"), ("M51.14", "Thoracic intervertebral disc disorder")],
    "lumbar spine": [("M54.5", "Low back pain"), ("M51.16", "Lumbar intervertebral disc degeneration"), ("M54.41", "Lumbago with sciatica, right side")],
    "right shoulder": [("M75.111", "Rotator cuff tear, right shoulder"), ("M25.511", "Pain in right shoulder")],
    "left shoulder": [("M75.112", "Rotator cuff tear, left shoulder"), ("M25.512", "Pain in left shoulder")],
    "right knee": [("S83.511A", "Sprain of ACL, right knee"), ("M23.211", "Derangement of meniscus, right knee")],
    "left knee": [("S83.512A", "Sprain of ACL, left knee"), ("M23.212", "Derangement of meniscus, left knee")],
    "right wrist": [("S62.001A", "Fracture of navicular bone, right wrist"), ("G56.01", "Carpal tunnel syndrome, right")],
    "left wrist": [("S62.002A", "Fracture of navicular bone, left wrist"), ("G56.02", "Carpal tunnel syndrome, left")],
    "right hand": [("S66.011A", "Strain of flexor muscle of right thumb"), ("G56.01", "Carpal tunnel syndrome, right")],
    "left hand": [("S66.012A", "Strain of flexor muscle of left thumb"), ("G56.02", "Carpal tunnel syndrome, left")],
    "right hip": [("M16.11", "Primary osteoarthritis, right hip"), ("M25.551", "Pain in right hip")],
    "left hip": [("M16.12", "Primary osteoarthritis, left hip"), ("M25.552", "Pain in left hip")],
    "right ankle": [("S93.401A", "Sprain of right ankle"), ("M25.571", "Pain in right ankle")],
    "left ankle": [("S93.402A", "Sprain of left ankle"), ("M25.572", "Pain in left ankle")],
    "right elbow": [("M77.11", "Lateral epicondylitis, right elbow"), ("M25.521", "Pain in right elbow")],
    "left elbow": [("M77.12", "Lateral epicondylitis, left elbow"), ("M25.522", "Pain in left elbow")],
    "right foot": [("S92.901A", "Fracture of right foot"), ("M79.671", "Pain in right foot")],
    "left foot": [("S92.902A", "Fracture of left foot"), ("M79.672", "Pain in left foot")],
    "psyche (anxiety)": [("F41.1", "Generalized anxiety disorder"), ("F43.10", "Post-traumatic stress disorder")],
    "psyche (depression)": [("F32.1", "Major depressive disorder, moderate"), ("F34.1", "Dysthymic disorder")],
    "psyche (PTSD)": [("F43.10", "Post-traumatic stress disorder, unspecified"), ("F43.12", "PTSD, chronic")],
    "psyche (sleep disorder)": [("G47.00", "Insomnia, unspecified"), ("G47.9", "Sleep disorder, unspecified")],
    "head/brain (TBI)": [("S06.0X0A", "Concussion without loss of consciousness"), ("S06.5X0A", "Traumatic subdural hemorrhage")],
    "hearing (bilateral)": [("H91.90", "Unspecified hearing loss, unspecified ear"), ("H83.3X9", "Noise effects on inner ear")],
    "lungs": [("J68.0", "Chemical bronchitis"), ("J84.10", "Pulmonary fibrosis, unspecified")],
    "sacrum/coccyx": [("M53.3", "Sacrococcygeal disorders"), ("S32.10XA", "Fracture of sacrum")],
    "jaw/TMJ": [("M26.60", "TMJ disorder, unspecified"), ("S02.60XA", "Fracture of mandible")],
    "face": [("S02.0XXA", "Fracture of vault of skull"), ("S01.81XA", "Laceration of face")],
    "vision (bilateral)": [("H53.9", "Unspecified visual disturbance"), ("T26.01XA", "Burn of right eyelid")],
    "heart": [("I25.10", "Atherosclerotic heart disease"), ("I21.9", "Acute myocardial infarction")],
    "kidneys": [("N17.9", "Acute kidney failure, unspecified")],
    "liver": [("K76.0", "Fatty liver, not elsewhere classified")],
    "gastrointestinal": [("K21.0", "GERD with esophagitis"), ("K59.00", "Constipation, unspecified")],
}

# Default ICD-10 for body parts not in the map
DEFAULT_ICD10 = [("M79.3", "Panniculitis, unspecified"), ("R29.898", "Other symptoms involving the musculoskeletal system")]

# Common CPT codes for WC procedures
CPT_CODES = {
    "office_visit": [("99213", "Office visit, established, low"), ("99214", "Office visit, established, moderate")],
    "spine_injection": [("64483", "Transforaminal epidural injection, lumbar"), ("62323", "Lumbar epidural steroid injection")],
    "mri": [("72148", "MRI lumbar spine w/o contrast"), ("72141", "MRI cervical spine w/o contrast"), ("73221", "MRI upper extremity joint")],
    "xray": [("72100", "X-ray lumbar spine, 2-3 views"), ("72040", "X-ray cervical spine, 2-3 views")],
    "surgery_spine": [("63030", "Lumbar laminotomy/discectomy"), ("22551", "Anterior cervical discectomy & fusion")],
    "surgery_shoulder": [("29827", "Arthroscopic rotator cuff repair"), ("23412", "Open rotator cuff repair")],
    "surgery_knee": [("29881", "Arthroscopic meniscectomy"), ("27447", "Total knee arthroplasty")],
    "physical_therapy": [("97110", "Therapeutic exercises"), ("97140", "Manual therapy"), ("97530", "Therapeutic activities")],
    "emg_ncv": [("95907", "Nerve conduction study, 1-2 nerves"), ("95910", "Nerve conduction study, 5-6 nerves")],
    "qme_eval": [("99456", "Work-related disability exam, established"), ("99455", "Work-related disability exam, initial")],
}

# Common WC medications
MEDICATIONS = [
    ("Gabapentin", "300mg", "TID"),
    ("Ibuprofen", "800mg", "TID"),
    ("Cyclobenzaprine", "10mg", "TID"),
    ("Meloxicam", "15mg", "QD"),
    ("Tramadol", "50mg", "Q6H PRN"),
    ("Diclofenac gel", "1%", "QID topical"),
    ("Amitriptyline", "25mg", "QHS"),
    ("Naproxen", "500mg", "BID"),
    ("Tizanidine", "4mg", "TID"),
    ("Pregabalin", "75mg", "BID"),
    ("Duloxetine", "60mg", "QD"),
    ("Methocarbamol", "750mg", "QID"),
    ("Omeprazole", "20mg", "QD"),
    ("Lidocaine patch", "5%", "12h on/12h off"),
]

# Injury mechanisms
INJURY_MECHANISMS = {
    "specific": [
        "Lifting heavy object (>50 lbs) resulting in acute onset",
        "Slip and fall on wet surface",
        "Struck by falling object from overhead",
        "Motor vehicle accident during work duties",
        "Fall from ladder/scaffolding",
        "Caught hand/arm in machinery",
        "Repetitive motion causing acute exacerbation",
        "Assault by patient/client/member of public",
        "Tripped over uneven surface/debris",
        "Overexertion during physical task",
    ],
    "cumulative_trauma": [
        "Repetitive lifting, bending, and twisting over course of employment",
        "Prolonged keyboard/mouse use causing cumulative upper extremity strain",
        "Continuous heavy labor causing progressive musculoskeletal deterioration",
        "Repetitive overhead work causing progressive shoulder dysfunction",
        "Prolonged standing/walking on hard surfaces causing lower extremity CT",
        "Chronic exposure to workplace stressors causing psychiatric injury",
    ],
}

# Work restriction descriptions
WORK_RESTRICTIONS = [
    "No lifting over 10 lbs",
    "No lifting over 25 lbs",
    "No repetitive bending or twisting",
    "No overhead reaching",
    "Sit/stand as needed",
    "No prolonged standing > 30 minutes",
    "No prolonged sitting > 45 minutes",
    "No climbing ladders or scaffolding",
    "Modified duty — sedentary only",
    "Off work — total temporary disability",
    "No forceful gripping or pinching",
    "May return to full duty with no restrictions",
    "Limited keyboarding to 30 minutes per hour",
    "No pushing/pulling > 20 lbs",
]

# AMA Guides WPI ratings (typical ranges by body part)
WPI_RATINGS = {
    "cervical spine": (5, 28),
    "lumbar spine": (5, 33),
    "thoracic spine": (3, 15),
    "shoulder": (5, 24),
    "knee": (3, 20),
    "wrist": (3, 15),
    "hand": (2, 12),
    "hip": (5, 25),
    "ankle": (3, 15),
    "elbow": (3, 12),
    "psyche": (5, 30),
}

# UR Decision templates
UR_DECISION_TYPES = ["Approved", "Modified", "Denied", "Deferred"]

# IMR Outcome templates
IMR_OUTCOMES = ["Upheld", "Modified", "Overturned"]

# Lien amount ranges by type
LIEN_AMOUNT_RANGES = {
    "medical_provider": (2500, 75000),
    "hospital": (10000, 250000),
    "pharmacy": (500, 15000),
    "attorney_costs": (1000, 25000),
    "ambulance": (1500, 8000),
    "self_procurement": (200, 5000),
    "edd_overpayment": (1000, 30000),
}

# PD Rating ranges (percentage) by body part
PD_RATING_RANGES = {
    "cervical spine": (5, 35),
    "lumbar spine": (5, 40),
    "thoracic spine": (3, 20),
    "shoulder": (5, 30),
    "knee": (5, 25),
    "wrist": (3, 18),
    "hand": (2, 15),
    "hip": (5, 30),
    "ankle": (3, 18),
    "elbow": (3, 15),
    "psyche": (10, 50),
    "head": (10, 60),
    "internal": (5, 40),
}

# TD Payment rate calculation constants
TD_RATE_MINIMUM = 242.86  # 2024 CA minimum TD rate (weekly)
TD_RATE_MAXIMUM = 1619.15  # 2024 CA maximum TD rate (weekly)

# PD Payment rate schedule
PD_RATE_MINIMUM = 160.00
PD_RATE_MAXIMUM = 290.00

# Settlement ranges by resolution type
SETTLEMENT_RANGES = {
    "stipulations": (15000, 150000),
    "c_and_r": (20000, 500000),
    "trial": (25000, 750000),
}

# Medicare Set-Aside ranges
MSA_RANGES = (5000, 100000)

# SJDB Voucher amounts by PD percentage
SJDB_VOUCHER_AMOUNTS = {
    (15, 24): 6000,
    (25, 49): 8000,
    (50, 99): 10000,
}

# Offer of work types
OFFER_OF_WORK_TYPES = ["regular", "modified", "alternative"]

# QME Panel specialties
QME_PANEL_SPECIALTIES = [
    "Orthopedic Surgery",
    "Pain Management",
    "Neurology",
    "Physical Medicine & Rehabilitation",
    "Psychiatry",
    "Internal Medicine",
    "Chiropractic",
    "Neurosurgery",
]

# California cities for addresses
CA_CITIES = [
    ("Los Angeles", "90001"), ("San Diego", "92101"), ("San Francisco", "94102"),
    ("Sacramento", "95814"), ("Fresno", "93721"), ("Long Beach", "90802"),
    ("Oakland", "94607"), ("Bakersfield", "93301"), ("Anaheim", "92801"),
    ("Santa Ana", "92701"), ("Riverside", "92501"), ("Stockton", "95202"),
    ("Irvine", "92614"), ("Chula Vista", "91910"), ("San Bernardino", "92401"),
    ("Modesto", "95354"), ("Fontana", "92335"), ("Moreno Valley", "92553"),
    ("Glendale", "91205"), ("Huntington Beach", "92648"),
    ("Pasadena", "91101"), ("Pomona", "91766"), ("Torrance", "90501"),
    ("Escondido", "92025"), ("Ventura", "93001"),
]
