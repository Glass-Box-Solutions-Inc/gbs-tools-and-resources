"""
Deposition Q&A exchange pools organized by topic area for Workers' Compensation
deposition transcript generation.

Pools use {placeholder} tokens substituted from case data at generation time.
Generates 80-150 Q&A exchanges per deposition for realistic 10-30 page transcripts.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from typing import Any

# ---------------------------------------------------------------------------
# Q&A Exchange Pools by Topic Area
# ---------------------------------------------------------------------------

PERSONAL_BACKGROUND: list[tuple[str, str]] = [
    (
        "Good morning. Could you please state your full name for the record?",
        "{full_name}.",
    ),
    (
        "And what is your date of birth?",
        "{dob}.",
    ),
    (
        "How old are you currently?",
        "I am {age} years old.",
    ),
    (
        "Are you married?",
        "{marital_status}.",
    ),
    (
        "Do you have any children?",
        "{children_answer}.",
    ),
    (
        "What is your Social Security number? Just the last four digits for the record.",
        "The last four are {ssn_last_four}.",
    ),
    (
        "Have you ever been known by any other name?",
        "No, I've always gone by {full_name}.",
    ),
    (
        "What languages do you speak?",
        "English{second_language}.",
    ),
]

ADDRESS_LIVING: list[tuple[str, str]] = [
    (
        "What is your current home address?",
        "{address}.",
    ),
    (
        "How long have you lived at your current address?",
        "I've been there for about {years_at_address}.",
    ),
    (
        "Do you rent or own your home?",
        "I {rent_own}.",
    ),
    (
        "Who else lives with you at that address?",
        "{household_answer}.",
    ),
    (
        "Have you moved since the date of injury?",
        "{moved_answer}.",
    ),
]

EDUCATION: list[tuple[str, str]] = [
    (
        "What is the highest level of education you completed?",
        "{education_level}.",
    ),
    (
        "Did you receive any vocational training or certifications?",
        "{vocational_training}.",
    ),
    (
        "Did you attend any trade school or specialized training?",
        "{trade_school_answer}.",
    ),
    (
        "Do you have any professional licenses or certifications?",
        "{licenses_answer}.",
    ),
]

PRIOR_EMPLOYMENT: list[tuple[str, str]] = [
    (
        "Before working for {employer}, where were you employed?",
        "Before that, I worked at {prior_employer} for about {prior_years}.",
    ),
    (
        "What did you do at {prior_employer}?",
        "I was a {prior_position}. Mostly {prior_duties}.",
    ),
    (
        "Why did you leave {prior_employer}?",
        "{prior_leave_reason}.",
    ),
    (
        "Were you ever injured while working at {prior_employer}?",
        "No, I never had any work injuries before this one.",
    ),
    (
        "How would you describe your physical health before you started at {employer}?",
        "I was in good health. I had no problems doing physical work.",
    ),
    (
        "Did you have any restrictions on the type of work you could do before working at {employer}?",
        "No, I had no restrictions at all.",
    ),
]

CURRENT_EMPLOYER: list[tuple[str, str]] = [
    (
        "When did you begin working for {employer}?",
        "I started on {hire_date}.",
    ),
    (
        "What was your position or job title at {employer}?",
        "I was a {position}.",
    ),
    (
        "Can you describe your typical job duties?",
        "My typical day involved {job_duties}. It was {physical_level} work.",
    ),
    (
        "How many hours per week did you typically work?",
        "I worked about {weekly_hours} hours per week, usually {schedule}.",
    ),
    (
        "What was your hourly rate of pay at the time of injury?",
        "I was making ${hourly_rate} per hour.",
    ),
    (
        "Did you receive any benefits through your employer?",
        "Yes, I had {benefits}.",
    ),
    (
        "Describe a typical work day for me from start to finish.",
        "I would usually start at {start_time}. First, I would {morning_task}. Then throughout the day I would {day_task}. My shift ended around {end_time}.",
    ),
    (
        "What was the most physically demanding part of your job?",
        "The {demanding_task}. That was the hardest part of the job.",
    ),
    (
        "Did you like your job?",
        "{job_satisfaction}.",
    ),
    (
        "Did you have any performance issues or disciplinary actions at {employer}?",
        "No, my record was clean. I always got good reviews.",
    ),
    (
        "Who was your direct supervisor?",
        "My supervisor was {supervisor_name}.",
    ),
]

INJURY_INCIDENT: list[tuple[str, str]] = [
    (
        "I'd like to ask you about the incident on {doi}. Can you tell me exactly what happened?",
        "{injury_description} I immediately felt pain in my {body_parts}.",
    ),
    (
        "What time of day did this happen?",
        "It was around {injury_time} in the {time_of_day}.",
    ),
    (
        "Were there any witnesses to the incident?",
        "{witnesses_answer}.",
    ),
    (
        "Did you report the injury to your supervisor?",
        "Yes, I reported it {report_timing}. I told {report_to} what happened.",
    ),
    (
        "How did you report it? Was it verbal, written, or both?",
        "I told {report_to} verbally right away, and then {written_report}.",
    ),
    (
        "Was an incident report or accident report filled out?",
        "{incident_report_answer}.",
    ),
    (
        "Were you able to finish your shift that day?",
        "{finish_shift_answer}.",
    ),
    (
        "Did you go to the emergency room or urgent care that day?",
        "{er_visit_answer}.",
    ),
    (
        "What were the first symptoms you experienced?",
        "Right away I felt {initial_symptoms}.",
    ),
    (
        "Did the pain come on suddenly or gradually?",
        "{pain_onset}.",
    ),
    (
        "Have you ever had a similar injury before?",
        "No, nothing like this before.",
    ),
    (
        "Were you wearing any safety equipment at the time?",
        "{safety_equipment_answer}.",
    ),
    (
        "Was there anything about the work environment that contributed to this injury?",
        "{environment_factor}.",
    ),
]

MEDICAL_TREATMENT: list[tuple[str, str]] = [
    (
        "Who was the first doctor you saw for this injury?",
        "The first doctor I saw was Dr. {treating_physician} at {facility}.",
    ),
    (
        "How often do you see Dr. {treating_physician_last}?",
        "I see Dr. {treating_physician_last} about {visit_frequency}.",
    ),
    (
        "What treatments has Dr. {treating_physician_last} provided?",
        "Dr. {treating_physician_last} has provided {treatments}.",
    ),
    (
        "Have you been referred to any specialists?",
        "{specialist_referral}.",
    ),
    (
        "Have you had any physical therapy?",
        "{pt_answer}.",
    ),
    (
        "How many physical therapy sessions have you had?",
        "I've had about {pt_sessions} sessions so far.",
    ),
    (
        "Has physical therapy helped?",
        "{pt_effectiveness}.",
    ),
    (
        "Have you had any injections for your injury?",
        "{injection_answer}.",
    ),
    (
        "Have you undergone any surgical procedures related to this injury?",
        "{surgery_answer}.",
    ),
    (
        "Has anyone recommended surgery to you?",
        "{surgery_recommendation}.",
    ),
    (
        "Have you had any diagnostic tests such as X-rays, MRIs, or CT scans?",
        "Yes, I've had {diagnostic_tests}.",
    ),
    (
        "What medications are you currently taking for your injury?",
        "I'm currently taking {current_medications}.",
    ),
    (
        "Do the medications help with your pain?",
        "{medication_effectiveness}.",
    ),
    (
        "Do you have any side effects from your medications?",
        "{medication_side_effects}.",
    ),
    (
        "Have you missed any medical appointments?",
        "No, I try to make it to all of my appointments.",
    ),
]

CURRENT_SYMPTOMS: list[tuple[str, str]] = [
    (
        "How would you describe your pain today?",
        "Today my pain is about a {pain_today}/10. {pain_quality_today}.",
    ),
    (
        "On a scale of 0 to 10, with 10 being the worst pain you can imagine, what is your average pain level?",
        "On average, it's about a {avg_pain}/10. Some days are better, some are worse.",
    ),
    (
        "What is the worst your pain gets?",
        "At its worst, it gets up to a {worst_pain}/10. That's usually when I {worst_pain_trigger}.",
    ),
    (
        "What makes your pain worse?",
        "{pain_aggravators}.",
    ),
    (
        "What helps relieve your pain?",
        "{pain_relievers}.",
    ),
    (
        "Do you experience any numbness or tingling?",
        "{numbness_answer}.",
    ),
    (
        "Do you have any weakness in the affected area?",
        "{weakness_answer}.",
    ),
    (
        "How is your sleep?",
        "{sleep_answer}.",
    ),
    (
        "Has this injury affected your mood or mental health?",
        "{mood_answer}.",
    ),
    (
        "Are you seeing anyone for anxiety or depression related to this injury?",
        "{mental_health_treatment}.",
    ),
]

DAILY_ACTIVITIES: list[tuple[str, str]] = [
    (
        "Walk me through a typical day for you now, from the time you wake up.",
        "I usually wake up around {wake_time}. {morning_routine}. The rest of the day I mostly {day_activities}.",
    ),
    (
        "Can you do your own cooking?",
        "{cooking_answer}.",
    ),
    (
        "Are you able to do laundry?",
        "{laundry_answer}.",
    ),
    (
        "Can you go grocery shopping?",
        "{shopping_answer}.",
    ),
    (
        "Are you able to drive?",
        "{driving_answer}.",
    ),
    (
        "Can you do yard work or household maintenance?",
        "{yard_work_answer}.",
    ),
    (
        "How do you spend most of your time during the day?",
        "Mostly I {daily_time}. I can't do much because of the pain.",
    ),
    (
        "Do you exercise or do any physical activities?",
        "{exercise_answer}.",
    ),
    (
        "Can you attend social events or visit friends and family?",
        "{social_answer}.",
    ),
    (
        "Do you use any assistive devices like a cane, brace, or walker?",
        "{assistive_devices}.",
    ),
]

FUNCTIONAL_LIMITATIONS: list[tuple[str, str]] = [
    (
        "What household chores can you no longer do because of this injury?",
        "I can't {cant_do_chores}. My {helper} has to do those things now.",
    ),
    (
        "Can you lift objects? If so, how much weight?",
        "{lifting_answer}.",
    ),
    (
        "How long can you sit in one position?",
        "{sitting_tolerance}.",
    ),
    (
        "How long can you stand in one place?",
        "{standing_tolerance}.",
    ),
    (
        "How far can you walk before you need to stop and rest?",
        "{walking_tolerance}.",
    ),
    (
        "Can you bend down to pick something up off the floor?",
        "{bending_answer}.",
    ),
    (
        "Can you reach overhead?",
        "{reaching_answer}.",
    ),
    (
        "Can you climb stairs?",
        "{stairs_answer}.",
    ),
    (
        "Has this injury affected your ability to care for yourself — bathing, dressing, that sort of thing?",
        "{self_care_answer}.",
    ),
]

PRIOR_MEDICAL: list[tuple[str, str]] = [
    (
        "Before this injury, did you have any problems with your {body_parts}?",
        "{prior_problems_answer}.",
    ),
    (
        "Have you ever filed a workers' compensation claim before?",
        "{prior_wc_claim}.",
    ),
    (
        "Have you ever been involved in a car accident?",
        "{car_accident_answer}.",
    ),
    (
        "Have you ever had any surgeries before this injury?",
        "{prior_surgeries}.",
    ),
    (
        "Were you taking any medications before this injury?",
        "{prior_medications}.",
    ),
    (
        "Did you see a doctor regularly before this injury?",
        "{prior_doctor_visits}.",
    ),
    (
        "Did you have any physical limitations before this injury?",
        "No, I was able to do everything without any problems.",
    ),
    (
        "Were you involved in any sports or recreational activities before the injury?",
        "{prior_activities}.",
    ),
]

WORK_STATUS: list[tuple[str, str]] = [
    (
        "Are you currently working?",
        "{work_status_answer}.",
    ),
    (
        "Has your doctor placed any work restrictions on you?",
        "Yes, I'm restricted to {work_restrictions}.",
    ),
    (
        "Has your employer offered you modified or light duty work?",
        "{modified_duty_answer}.",
    ),
    (
        "Are you receiving temporary disability payments?",
        "{td_answer}.",
    ),
    (
        "Do you want to return to your previous job?",
        "{return_to_work_desire}.",
    ),
    (
        "Do you believe you can return to your previous job?",
        "{return_to_work_belief}.",
    ),
]

CLOSING: list[tuple[str, str]] = [
    (
        "Is there anything else you think is important for me to know about this injury?",
        "{closing_statement}.",
    ),
    (
        "Have you told me the truth today in all of your answers?",
        "Yes, everything I said is true.",
    ),
    (
        "Is there anything you'd like to add or correct from your testimony today?",
        "No, I think I've covered everything.",
    ),
    (
        "Thank you for your time. We have nothing further at this time.",
        "Thank you.",
    ),
]

# ---------------------------------------------------------------------------
# Objections and Procedural Interjections
# ---------------------------------------------------------------------------

OBJECTIONS: list[str] = [
    "Objection, calls for speculation.",
    "Objection, asked and answered.",
    "Objection, the question assumes facts not in evidence.",
    "Objection, vague and ambiguous.",
    "Objection, compound question.",
    "Objection, calls for a narrative response.",
    "Objection, leading.",
    "Objection, relevance.",
    "Objection, the question is overly broad.",
    "Objection, calls for a legal conclusion.",
    "Objection. Counsel, could you rephrase the question?",
    "I'll object to the form of the question, but the witness may answer.",
]

EXHIBIT_REFERENCES: list[str] = [
    "Let me hand you what's been marked as Exhibit {n}. Do you recognize this document?",
    "I'm going to show you Exhibit {n}. Can you identify this for the record?",
    "Directing your attention to Exhibit {n}, which has been previously marked. Is this your signature at the bottom of the page?",
    "I'd like you to take a look at Exhibit {n}. Is this the medical report from Dr. {physician}?",
    "Exhibit {n} has been marked for identification. Is this a copy of your job description at {employer}?",
]

TIME_MARKERS: list[str] = [
    "(Recess taken at {time}.)",
    "(Off the record at {time}. Back on the record at {resume_time}.)",
    "(Brief recess taken.)",
    "(Discussion held off the record.)",
    "(Witness takes a moment to compose herself/himself.)",
]

# ---------------------------------------------------------------------------
# Placeholder Default Values (for filling templates)
# ---------------------------------------------------------------------------

_DEFAULT_VALUES: dict[str, list[str]] = {
    "marital_status": ["Yes, I'm married", "No, I'm not married", "I'm divorced", "I'm single"],
    "children_answer": ["Yes, I have two children", "Yes, I have three kids", "No, I don't have children", "Yes, one child"],
    "second_language": ["", " and some Spanish", ""],
    "years_at_address": ["two years", "about five years", "three years", "since 2020"],
    "rent_own": ["rent", "own my home", "rent an apartment"],
    "household_answer": ["My wife and two kids", "I live alone", "My spouse", "My partner and our child"],
    "moved_answer": ["No, I've been at the same address", "No, same address", "Yes, I had to move to a single-story home because of the injury"],
    "education_level": ["I graduated high school", "I have a GED", "I completed some college", "I have a high school diploma"],
    "vocational_training": ["No, just on-the-job training", "I completed a certification program for my trade", "No formal vocational training"],
    "trade_school_answer": ["No", "Yes, I went to trade school for welding", "No, I learned everything on the job"],
    "licenses_answer": ["I have a forklift certification", "Just my driver's license", "No professional licenses"],
    "prior_employer": ["another company in the same industry", "a different employer"],
    "prior_years": ["three years", "two years", "five years"],
    "prior_position": ["similar type of worker", "laborer", "helper"],
    "prior_duties": ["the same type of physical work", "similar physical tasks"],
    "prior_leave_reason": ["I found a better opportunity at {employer}", "The position was temporary", "I was laid off due to downsizing"],
    "job_duties": ["handling materials and operating equipment", "physical labor including lifting, carrying, and moving items", "standing on my feet all day dealing with customers and stocking shelves"],
    "physical_level": ["pretty physical", "very physical", "moderately physical"],
    "weekly_hours": ["40", "40 to 45", "around 40"],
    "schedule": ["Monday through Friday", "five days a week with occasional overtime", "a rotating schedule"],
    "hourly_rate": ["{hourly_rate}"],
    "benefits": ["health insurance and vacation time", "medical, dental, and paid time off", "basic health insurance"],
    "start_time": ["6 AM", "7 AM", "8 AM", "7:30 AM"],
    "morning_task": ["check in and get my assignments", "clock in and start setting up", "get my equipment ready"],
    "day_task": ["perform my regular duties", "handle various tasks as assigned", "work through my responsibilities"],
    "end_time": ["2:30 PM", "3:30 PM", "4:00 PM", "5:00 PM"],
    "demanding_task": ["heavy lifting", "repetitive bending and lifting", "being on my feet all day", "overhead work"],
    "job_satisfaction": ["Yes, I liked my job. I was good at it", "It was hard work but I enjoyed it", "Yes, it was a good job"],
    "injury_time": ["10 in the morning", "around 2 PM", "mid-morning", "early afternoon"],
    "time_of_day": ["morning", "afternoon"],
    "witnesses_answer": ["Yes, my coworker saw what happened", "I think a couple of people were nearby", "Yes, my supervisor was right there"],
    "report_timing": ["right away", "immediately", "the same day", "within the hour"],
    "report_to": ["my supervisor", "the shift manager", "my foreman"],
    "written_report": ["I filled out an incident report later that day", "they had me fill out a form", "a written report was done by the supervisor"],
    "incident_report_answer": ["Yes, I filled one out that same day", "Yes, my supervisor handled the paperwork"],
    "finish_shift_answer": ["No, I had to leave early because of the pain", "I tried to finish but couldn't", "No, they sent me home right away", "I finished my shift but I was in a lot of pain"],
    "er_visit_answer": ["Yes, I went to the emergency room that same day", "I saw a doctor the next day", "Yes, my supervisor drove me to urgent care"],
    "initial_symptoms": ["sharp pain and I could barely move", "intense pain and tightness", "severe pain and some numbness"],
    "pain_onset": ["It was immediate. I felt it right when it happened", "The sharp pain hit me instantly"],
    "safety_equipment_answer": ["Yes, I was wearing my standard safety gear", "I was wearing gloves and safety boots", "Yes, all required safety equipment"],
    "environment_factor": ["The area was wet and I had mentioned it before", "It was a normal work environment", "Nothing unusual that day"],
    "visit_frequency": ["every two weeks", "once a month", "every three weeks", "weekly"],
    "treatments": ["physical therapy, medications, and injections", "medications and physical therapy", "conservative treatment including PT and medications"],
    "specialist_referral": ["Yes, I was referred to a pain management specialist", "I've seen an orthopedic surgeon", "Yes, I've been to a few specialists"],
    "pt_answer": ["Yes, I've been going to physical therapy regularly", "Yes, I've had quite a few sessions"],
    "pt_sessions": ["about 20", "around 15", "more than 25", "about 18"],
    "pt_effectiveness": ["It helps a little bit but doesn't take the pain away completely", "Some exercises help, but my pain always comes back", "It provides temporary relief"],
    "injection_answer": ["Yes, I've had cortisone injections", "I've had a few epidural injections", "Yes, I've had injections but they only helped for a short time"],
    "surgery_answer": ["No, not yet", "No, but it has been discussed", "Yes, I had surgery on my {body_parts}"],
    "surgery_recommendation": ["My doctor has mentioned it as a possibility if I don't improve", "Not yet, we're still trying conservative treatment", "Yes, Dr. {treating_physician_last} wants me to have surgery"],
    "diagnostic_tests": ["X-rays and an MRI", "MRI and CT scan", "several X-rays and two MRIs"],
    "current_medications": ["pain medication, a muscle relaxer, and anti-inflammatory", "gabapentin and ibuprofen", "prescription pain meds and a nerve medication"],
    "medication_effectiveness": ["They take the edge off but don't eliminate the pain", "They help somewhat but I still have a lot of pain", "Moderately. I still have pain every day"],
    "medication_side_effects": ["The medications make me drowsy sometimes", "I get some stomach issues from the anti-inflammatory", "Yes, drowsiness and some dizziness"],
    "pain_today": ["6", "7", "5", "7"],
    "pain_quality_today": ["It's a constant ache with some sharp pains when I move certain ways", "Dull and throbbing most of the time"],
    "avg_pain": ["6", "7", "5"],
    "worst_pain": ["8", "9", "9"],
    "worst_pain_trigger": ["try to lift something or bend down", "overdo it with activity", "have been sitting or standing too long"],
    "pain_aggravators": ["Lifting, bending, prolonged sitting, and standing make it worse", "Physical activity, cold weather, and stress increase the pain"],
    "pain_relievers": ["Rest, ice, and my medications help somewhat", "Lying down, taking my medication, and heat packs", "Rest and medication, but nothing eliminates it completely"],
    "numbness_answer": ["Yes, I get numbness and tingling down my leg sometimes", "Yes, in my arm and hand", "Occasionally, especially at night"],
    "weakness_answer": ["Yes, my arm/leg feels weaker than before", "I notice weakness when I try to grip or lift things", "Some weakness, yes"],
    "sleep_answer": ["Terrible. I can't get comfortable. I wake up multiple times a night", "I have trouble falling asleep and staying asleep because of the pain", "Very poor. Maybe 4-5 hours a night"],
    "mood_answer": ["Yes, I feel depressed and frustrated. I can't do the things I used to do", "It's been very hard mentally. I feel anxious and down", "Yes, I've been struggling emotionally"],
    "mental_health_treatment": ["No, not yet, but my doctor has suggested it", "I'm going to start counseling soon", "I've been seeing a therapist for a few months now"],
    "wake_time": ["7 AM", "8 AM", "6:30 AM"],
    "morning_routine": ["It takes me a while to get going because of the stiffness. I take my medications and try to stretch a little", "I'm usually pretty stiff in the morning. I take a hot shower and my pills"],
    "day_activities": ["rest, watch TV, and try to do light things around the house", "sit around because I can't do much. I read or watch TV"],
    "cooking_answer": ["Simple things, yes. But I can't stand long enough to cook a full meal", "I can make basic things but my family cooks most meals now"],
    "laundry_answer": ["I can do light loads but I can't carry the basket. My wife helps me", "With difficulty. I need help lifting the basket"],
    "shopping_answer": ["I can go but I can't push a full cart or carry bags", "My spouse does most of the shopping now"],
    "driving_answer": ["I can drive short distances but long drives are painful", "Yes, but only for about 20-30 minutes before the pain gets too bad"],
    "yard_work_answer": ["No, I can't do any yard work anymore", "I can do very light things but nothing physical"],
    "daily_time": ["rest and try to manage my pain", "watch TV and do small tasks around the house"],
    "exercise_answer": ["No, I can't exercise like I used to. I try to walk a little but that's it", "Just the exercises my physical therapist gave me"],
    "social_answer": ["Not really. I avoid going out because I'm in too much pain", "Very rarely. I've become more isolated since the injury"],
    "assistive_devices": ["I use a back brace sometimes", "No assistive devices right now", "I sometimes use a cane on bad days"],
    "cant_do_chores": ["vacuum, mop, take out the trash, or do yard work", "lift anything heavy, bend down to clean, or do laundry"],
    "helper": ["wife", "husband", "family", "spouse"],
    "lifting_answer": ["Maybe 5-10 pounds. Nothing heavy", "I try not to lift more than about 10 pounds"],
    "sitting_tolerance": ["About 20-30 minutes, then I have to get up and move around", "Maybe 30 minutes at most before the pain gets too bad"],
    "standing_tolerance": ["About 15-20 minutes", "Not long. Maybe 10-15 minutes before I need to sit down"],
    "walking_tolerance": ["I can walk about a block or two before I need to stop", "Maybe 10-15 minutes of walking"],
    "bending_answer": ["With great difficulty. It causes a lot of pain", "I try to avoid it. I use a grabber tool"],
    "reaching_answer": ["Not very well. It causes pain and I can't reach as high as before", "It's painful and limited"],
    "stairs_answer": ["One flight with difficulty. I use the handrail", "Very slowly and painfully. I avoid stairs when possible"],
    "self_care_answer": ["On bad days, yes. I need help getting dressed and bathing", "I manage most days but it takes me longer and some days I need help"],
    "prior_problems_answer": ["No, never. I was perfectly healthy before this", "No, I had no issues at all before this injury", "No prior problems whatsoever"],
    "prior_wc_claim": ["No, this is my first claim", "Never. This is the first time", "No, I've never filed a workers' comp claim before"],
    "car_accident_answer": ["No", "No, never been in a car accident", "No car accidents"],
    "prior_surgeries": ["No, I've never had surgery", "No prior surgeries", "I had my appendix out years ago but nothing related to this"],
    "prior_medications": ["Nothing, I was healthy", "Just an occasional Advil for headaches", "No prescription medications"],
    "prior_doctor_visits": ["Just regular check-ups. Nothing serious", "Yearly physical, that's about it"],
    "prior_activities": ["Yes, I used to go hiking and play basketball", "I was pretty active. I liked to work out and play sports", "I used to enjoy gardening and walking"],
    "work_status_answer": ["No, I have been off work since the injury", "No, I'm currently not working", "I tried to go back on modified duty but couldn't handle it"],
    "work_restrictions": ["light duty only, no lifting over 10 pounds", "sedentary work only", "no lifting, no bending, sit/stand as needed"],
    "modified_duty_answer": ["They offered modified duty but it wasn't really within my restrictions", "No, they haven't offered anything", "Yes, but the modified work still aggravated my condition"],
    "td_answer": ["Yes, I'm receiving temporary disability", "Yes, I get TD payments biweekly"],
    "return_to_work_desire": ["I would love to go back to work if I could. I miss working", "Yes, I want to work, but I don't know if I'll be able to"],
    "return_to_work_belief": ["Honestly, I don't think I can go back to the same type of work", "I hope so, but my doctor says it's unlikely I can do the same job"],
    "closing_statement": ["Just that this injury has completely changed my life and I'm doing everything I can to get better", "I just want to get better and go back to being able to provide for my family"],
}


# ---------------------------------------------------------------------------
# Generator Function
# ---------------------------------------------------------------------------

def _fill_template(text: str, case_data: dict[str, str]) -> str:
    """Fill {placeholder} tokens in text with case data or defaults."""
    result = text
    for key, value in case_data.items():
        result = result.replace(f"{{{key}}}", str(value))
    # Fill any remaining placeholders with defaults
    for key, options in _DEFAULT_VALUES.items():
        placeholder = f"{{{key}}}"
        if placeholder in result:
            result = result.replace(placeholder, random.choice(options))
    return result


def generate_deposition_exchanges(
    case: Any,
    min_exchanges: int = 80,
    max_exchanges: int = 150,
) -> list[tuple[str, str]]:
    """Generate a full deposition transcript Q&A exchange list.

    Draws from topic pools and fills placeholders with case data.
    Returns list of (question, answer) tuples.
    """
    injury = case.injuries[0] if case.injuries else None
    body_parts_str = ", ".join(injury.body_parts[:3]) if injury else "the injured area"

    # Build case data dict for placeholder substitution
    case_data: dict[str, str] = {
        "full_name": case.applicant.full_name,
        "dob": case.applicant.date_of_birth.strftime("%B %d, %Y"),
        "age": str((_today() - case.applicant.date_of_birth).days // 365),
        "ssn_last_four": case.applicant.ssn_last_four,
        "address": f"{case.applicant.address_street}, {case.applicant.address_city}, California, {case.applicant.address_zip}",
        "employer": case.employer.company_name,
        "hire_date": case.employer.hire_date.strftime("%B %d, %Y"),
        "position": case.employer.position,
        "hourly_rate": f"{case.employer.hourly_rate:.2f}",
        "doi": injury.date_of_injury.strftime("%B %d, %Y") if injury else "the date of injury",
        "injury_description": injury.description if injury else "I was injured at work.",
        "body_parts": body_parts_str,
        "treating_physician": case.treating_physician.full_name,
        "treating_physician_last": case.treating_physician.last_name,
        "facility": case.treating_physician.facility,
        "physician": case.treating_physician.last_name,
    }

    exchanges: list[tuple[str, str]] = []

    # Build from topic pools in deposition order
    topic_pools = [
        ("PERSONAL BACKGROUND", PERSONAL_BACKGROUND, 6, 8),
        ("ADDRESS AND LIVING SITUATION", ADDRESS_LIVING, 4, 5),
        ("EDUCATION", EDUCATION, 3, 4),
        ("PRIOR EMPLOYMENT", PRIOR_EMPLOYMENT, 4, 6),
        ("EMPLOYMENT AT {employer}", CURRENT_EMPLOYER, 8, 11),
        ("INJURY INCIDENT", INJURY_INCIDENT, 10, 13),
        ("MEDICAL TREATMENT", MEDICAL_TREATMENT, 12, 15),
        ("CURRENT SYMPTOMS", CURRENT_SYMPTOMS, 8, 10),
        ("DAILY ACTIVITIES AND LIFESTYLE", DAILY_ACTIVITIES, 8, 10),
        ("FUNCTIONAL LIMITATIONS", FUNCTIONAL_LIMITATIONS, 7, 9),
        ("PRIOR MEDICAL HISTORY", PRIOR_MEDICAL, 6, 8),
        ("WORK STATUS", WORK_STATUS, 5, 6),
        ("CLOSING", CLOSING, 3, 4),
    ]

    target = random.randint(min_exchanges, max_exchanges)

    for _topic_name, pool, min_from_pool, max_from_pool in topic_pools:
        # Scale selection to hit target
        count = min(random.randint(min_from_pool, max_from_pool), len(pool))
        selected = random.sample(pool, count)
        for q_template, a_template in selected:
            q = _fill_template(f"Q. {q_template}", case_data)
            a = _fill_template(f"A. {a_template}", case_data)
            exchanges.append((q, a))

    # Trim or pad to target range
    if len(exchanges) > target:
        # Keep first few and last few, trim middle
        keep_start = 10
        keep_end = 5
        middle = exchanges[keep_start:-keep_end]
        random.shuffle(middle)
        exchanges = exchanges[:keep_start] + middle[:target - keep_start - keep_end] + exchanges[-keep_end:]
    elif len(exchanges) < min_exchanges:
        # Pad with additional follow-up questions from all pools
        pad_pools = [CURRENT_SYMPTOMS, DAILY_ACTIVITIES, FUNCTIONAL_LIMITATIONS,
                     MEDICAL_TREATMENT, INJURY_INCIDENT, PRIOR_MEDICAL, WORK_STATUS]
        # Also add follow-up phrasing to avoid exact duplicates
        follow_up_prefixes = [
            "Let me go back to something you said earlier. ",
            "I want to clarify something. ",
            "Just to make sure I understand, ",
            "Going back to your earlier testimony, ",
            "Can you elaborate on that? ",
        ]
        while len(exchanges) < min_exchanges:
            pool = random.choice(pad_pools)
            q_t, a_t = random.choice(pool)
            prefix = random.choice(follow_up_prefixes) if random.random() > 0.5 else ""
            q = _fill_template(f"Q. {prefix}{q_t}", case_data)
            a = _fill_template(f"A. {a_t}", case_data)
            exchanges.append((q, a))

    return exchanges


def generate_objection() -> str:
    """Generate a random objection interjection."""
    return random.choice(OBJECTIONS)


def generate_exhibit_reference(n: int, case: Any) -> str:
    """Generate an exhibit reference with number filled in."""
    template = random.choice(EXHIBIT_REFERENCES)
    return template.format(
        n=n,
        physician=case.treating_physician.last_name if case.treating_physician else "Smith",
        employer=case.employer.company_name,
    )


def generate_time_marker() -> str:
    """Generate a realistic time marker for breaks during deposition."""
    hour = random.randint(10, 14)
    minute = random.randint(0, 59)
    resume_minute = minute + random.randint(5, 15)
    time_str = f"{hour}:{minute:02d} {'A.M.' if hour < 12 else 'P.M.'}"
    resume_hour = hour if resume_minute < 60 else hour + 1
    resume_minute = resume_minute % 60
    resume_str = f"{resume_hour}:{resume_minute:02d} {'A.M.' if resume_hour < 12 else 'P.M.'}"
    template = random.choice(TIME_MARKERS)
    return template.format(time=time_str, resume_time=resume_str)


def _today():
    """Get today's date (separated for testability)."""
    from datetime import date
    return date.today()
