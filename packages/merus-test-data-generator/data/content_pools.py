"""
Specialty-specific content pools for realistic CA WC document generation.

Provides body-region-keyed exam findings, clinical rationale, treatment narratives,
ROM normal values, and chronology descriptions. All templates draw from these pools
to produce varied, specialty-appropriate clinical language.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from typing import Any

# ---------------------------------------------------------------------------
# Physical Exam Pools by Specialty
# ---------------------------------------------------------------------------

ORTHOPEDIC_EXAM: dict[str, list[str]] = {
    "spine_cervical": [
        "Cervical range of motion is limited in flexion, extension, and bilateral lateral bending.",
        "Palpation reveals paravertebral muscle spasm at C5-C7 with tenderness to palpation.",
        "Spurling's test is positive on the right with reproduction of radicular symptoms into the right upper extremity.",
        "Spurling's test is negative bilaterally; no radicular symptoms reproduced.",
        "Lhermitte's sign is negative; no electric-shock sensation with cervical flexion.",
        "Cervical distraction test is positive, reducing radicular symptoms.",
        "Motor strength is 4/5 in the right deltoid (C5) and 4/5 in the right biceps (C6).",
        "Motor strength is 5/5 throughout bilateral upper extremities in all tested myotomes.",
        "Sensation is diminished to light touch in the C6 dermatome on the right.",
        "Deep tendon reflexes are 2+ and symmetric at the biceps (C5-C6) and triceps (C7) bilaterally.",
        "Deep tendon reflexes are 1+ at the right brachioradialis (C5-C6), diminished compared to left.",
        "Hoffmann's sign is negative bilaterally, ruling out upper motor neuron lesion.",
        "Patient demonstrates limited cervical rotation to the right, measuring 55 degrees versus 80 degrees normal.",
        "Tenderness is noted at the bilateral trapezius and levator scapulae muscle insertions.",
        "Cervical paraspinal musculature is in spasm bilaterally, more prominent on the right.",
        "No step-off deformity is palpated along the cervical spinous processes.",
        "Axial compression test reproduces neck pain without radicular component.",
        "Shoulder depression test is positive on the right, suggesting cervical root irritation.",
        "The patient holds the cervical spine in slight flexion and avoids extension.",
        "Upper extremity tension test (ULTT) is positive for median nerve bias on the right.",
        "Grip strength testing reveals 35 kg on the right versus 48 kg on the left.",
        "Interscapular pain is reproduced with resisted cervical extension.",
        "Palpation of the facet joints at C4-C5 and C5-C6 reproduces concordant pain.",
        "No vertebral artery signs with sustained cervical rotation testing.",
        "Clonus is absent at the wrists bilaterally.",
        "Jackson's compression test is positive on the right, reproducing radicular arm pain.",
        "Cervical flexion is measured at 40 degrees (normal 80 degrees), limited by pain.",
        "Cervical extension is measured at 30 degrees (normal 50 degrees), limited by muscle guarding.",
        "Bilateral lateral flexion is measured at 30 degrees right and 35 degrees left (normal 45 degrees).",
        "Cervical rotation is measured at 55 degrees bilaterally (normal 80 degrees).",
    ],
    "spine_lumbar": [
        "Lumbar range of motion is significantly restricted in all planes.",
        "Straight leg raise test is positive on the left at 35 degrees with reproduction of radicular symptoms.",
        "Straight leg raise is positive bilaterally at 40 degrees with concordant leg pain.",
        "Crossed straight leg raise is positive on the left, highly suggestive of disc herniation.",
        "Straight leg raise is negative bilaterally to 80 degrees.",
        "Lumbar flexion is measured at 35 degrees (normal 60 degrees) with pain at end range.",
        "Lumbar extension is measured at 10 degrees (normal 25 degrees), severely limited by pain.",
        "Lateral flexion is measured at 15 degrees bilaterally (normal 25 degrees).",
        "Lumbar rotation is measured at 20 degrees bilaterally (normal 30 degrees).",
        "Palpation reveals tenderness at the L4-L5 and L5-S1 levels with paravertebral spasm.",
        "Percussion tenderness is noted at the L4-L5 spinous process.",
        "Motor strength is 4/5 in the left extensor hallucis longus (L5) and 4/5 in the left tibialis anterior (L4).",
        "Motor strength is 5/5 in bilateral lower extremities across all myotomes L2-S1.",
        "Sensation is diminished to light touch and pinprick in the L5 dermatome on the left.",
        "Ankle jerk reflex is 1+ on the left (S1), diminished compared to 2+ on the right.",
        "Deep tendon reflexes are 2+ and symmetric at the knees (L3-L4) and ankles (S1) bilaterally.",
        "Waddell's signs are 0 out of 5, no evidence of symptom magnification.",
        "Waddell's signs are 1 out of 5 (superficial tenderness only), not clinically significant.",
        "Patrick's (FABER) test is negative bilaterally, ruling out hip pathology as pain source.",
        "Gaenslen's test is negative bilaterally; no SI joint dysfunction demonstrated.",
        "Prone instability test is positive, suggesting lumbar segmental instability.",
        "Slump test is positive on the left, reproducing concordant radicular leg pain.",
        "Gait is antalgic with reduced stride length and guarded posture.",
        "Patient is unable to heel-walk on the left side, suggesting L5 weakness.",
        "Toe walking is intact bilaterally, S1 motor function is preserved.",
        "Trendelenburg test is negative bilaterally; gluteus medius function is intact.",
        "Femoral nerve stretch test is negative bilaterally.",
        "Paraspinal muscles are in spasm bilaterally in the lumbar region, more prominent on the left.",
        "Sciatic notch tenderness is present on the left.",
        "Lumbar lordosis is flattened, consistent with protective muscle guarding.",
        "Patient demonstrates difficulty transitioning from seated to standing position.",
        "Sacroiliac compression and distraction tests are negative.",
    ],
    "shoulder": [
        "Neer's impingement sign is positive on the right, reproducing anterior shoulder pain.",
        "Hawkins-Kennedy test is positive on the right, suggesting subacromial impingement.",
        "Empty can test (Jobe's) is positive with weakness and pain in the right supraspinatus.",
        "Drop arm test is negative; patient can slowly lower arm from full abduction.",
        "External rotation lag sign is negative; infraspinatus function is intact.",
        "Speed's test is positive with tenderness over the long head of the biceps tendon.",
        "Yergason's test is positive, reproducing bicipital groove tenderness on the right.",
        "O'Brien's test is positive, suggesting possible superior labral pathology.",
        "Anterior apprehension test is negative; no instability demonstrated.",
        "Sulcus sign is negative bilaterally; no inferior glenohumeral laxity.",
        "Cross-body adduction test is positive, suggesting AC joint pathology on the right.",
        "Active forward flexion is measured at 140 degrees on the right (normal 180 degrees).",
        "Active abduction is measured at 130 degrees on the right (normal 180 degrees).",
        "Internal rotation is measured at 50 degrees on the right (normal 80 degrees).",
        "External rotation is measured at 60 degrees on the right (normal 90 degrees).",
        "Painful arc is noted between 70 and 120 degrees of abduction on the right.",
        "Motor strength is 4/5 in right shoulder abduction and external rotation.",
        "Motor strength is 4-/5 in right shoulder forward flexion against resistance.",
        "Palpation reveals tenderness at the right greater tuberosity and subacromial space.",
        "AC joint is tender to palpation on the right with no visible deformity.",
        "Scapular winging is not observed; serratus anterior function is intact.",
        "Passive range of motion exceeds active range of motion, suggesting rotator cuff weakness.",
        "Crepitus is noted with active shoulder motion on the right.",
        "Lift-off test is negative; subscapularis function is intact.",
        "Bear hug test is negative for subscapularis pathology.",
        "Hornblower's sign is negative; teres minor function is intact.",
        "Infraspinatus strength is 4/5 on the right with pain at end range.",
        "Right shoulder demonstrates positive impingement cluster (Neer's, Hawkins-Kennedy, and painful arc).",
        "Shoulder abduction is limited by pain rather than mechanical block.",
        "Posterior capsule tightness is noted with limited cross-body adduction on the right.",
    ],
    "knee": [
        "Lachman's test is positive with a soft endpoint on the right, grade 2 ACL laxity.",
        "Lachman's test is negative with a firm endpoint bilaterally.",
        "Anterior drawer test is positive on the right with 8mm translation.",
        "Posterior drawer test is negative bilaterally; PCL is intact.",
        "McMurray's test is positive for medial meniscal pathology on the right with a palpable click.",
        "McMurray's test is negative bilaterally for both medial and lateral menisci.",
        "Apley's compression test is positive on the right, suggesting meniscal pathology.",
        "Valgus stress test is negative at 0 and 30 degrees; MCL is intact bilaterally.",
        "Varus stress test is negative at 0 and 30 degrees; LCL is intact bilaterally.",
        "Patellar grind test (Clarke's) is positive on the right with retropatellar crepitus.",
        "Patellar apprehension test is negative; no lateral patellar instability.",
        "Knee flexion is measured at 100 degrees on the right (normal 135 degrees), limited by pain.",
        "Knee extension is full at 0 degrees bilaterally.",
        "Mild to moderate joint effusion is noted in the right knee.",
        "No joint effusion is detected on ballottement or bulge testing.",
        "Medial joint line tenderness is present on palpation of the right knee.",
        "Lateral joint line tenderness is noted on the right knee.",
        "Quadriceps strength is 4/5 on the right with visible atrophy of the VMO.",
        "Thigh circumference is measured at 2 cm less on the right versus the left at 15 cm above the patella.",
        "Ober's test is positive on the right, indicating iliotibial band tightness.",
        "Thessaly test at 20 degrees is positive on the right for medial compartment pain.",
        "Pivot shift test is negative bilaterally.",
        "Crepitus is noted with active knee flexion and extension on the right.",
        "The right knee demonstrates a small Baker's cyst on palpation of the popliteal fossa.",
        "Popliteal fossa is non-tender; no popliteal cyst palpated.",
        "Gait analysis reveals the patient favors the left lower extremity with shortened stance phase on the right.",
    ],
    "wrist_hand": [
        "Phalen's test is positive at 30 seconds on the right, reproducing paresthesias in the median nerve distribution.",
        "Phalen's test is negative bilaterally after 60 seconds.",
        "Tinel's sign is positive at the right carpal tunnel with tingling in digits 1-3.",
        "Tinel's sign is negative at the carpal tunnel bilaterally.",
        "Finkelstein's test is positive on the right, suggesting de Quervain's tenosynovitis.",
        "Grip strength (Jamar dynamometer): right 25 kg, left 42 kg (dominant right hand).",
        "Pinch strength (tip pinch): right 4 kg, left 7 kg.",
        "Two-point discrimination is 8mm in the right index finger (normal <6mm).",
        "Thenar atrophy is observed in the right hand, consistent with chronic median neuropathy.",
        "No thenar or hypothenar atrophy is observed.",
        "Allen's test demonstrates intact radial and ulnar artery patency bilaterally.",
        "Wrist flexion is measured at 50 degrees on the right (normal 80 degrees).",
        "Wrist extension is measured at 45 degrees on the right (normal 70 degrees).",
        "Radial deviation is measured at 15 degrees (normal 20 degrees).",
        "Ulnar deviation is measured at 20 degrees (normal 30 degrees).",
        "Digit flexion and extension are full in all digits of the right hand.",
        "The Watson (scaphoid shift) test is negative; no scapholunate instability.",
        "TFCC load test is negative; triangular fibrocartilage complex is stable.",
        "Durkan's compression test is positive over the right carpal tunnel.",
        "Semmes-Weinstein monofilament testing reveals diminished protective sensation in the right median distribution.",
        "Carpal tunnel compression test is positive at 20 seconds on the right.",
        "MCP, PIP, and DIP joints demonstrate full range of motion without crepitus.",
        "Tenderness is noted at the anatomical snuffbox on the right, ruling out scaphoid fracture is recommended.",
        "Intrinsic muscle testing is 5/5 in all compartments bilaterally.",
    ],
    "hip": [
        "Patrick's (FABER) test is positive on the right, reproducing groin pain.",
        "Internal rotation of the right hip is measured at 15 degrees (normal 40 degrees), limited by pain.",
        "External rotation of the right hip is measured at 30 degrees (normal 45 degrees).",
        "Hip flexion is measured at 90 degrees on the right (normal 120 degrees), limited by pain.",
        "Straight leg raise is negative for radicular symptoms but reproduces anterior hip pain at 60 degrees.",
        "Trendelenburg test is positive on the right, indicating gluteus medius weakness.",
        "Thomas test is positive on the right with a 15-degree hip flexion contracture.",
        "Ober's test is positive on the right, suggesting IT band and hip abductor tightness.",
        "Log roll test is positive on the right, suggesting intra-articular hip pathology.",
        "FADIR test (flexion, adduction, internal rotation) is positive on the right, suggesting labral pathology.",
        "Resisted hip flexion is 4/5 on the right with pain in the groin region.",
        "Palpation of the greater trochanter reproduces lateral hip pain.",
        "Gait analysis reveals an antalgic pattern with shortened stance phase on the right.",
        "Hip abductor strength is 3+/5 on the right.",
        "The patient demonstrates difficulty with single-leg stance on the right side.",
    ],
    "elbow": [
        "Lateral epicondyle is tender to palpation on the right (lateral epicondylitis).",
        "Medial epicondyle is tender to palpation (medial epicondylitis/golfer's elbow).",
        "Cozen's test is positive on the right with pain at the lateral epicondyle.",
        "Mill's test is positive for lateral epicondylitis on the right.",
        "Resisted wrist extension reproduces lateral elbow pain.",
        "Valgus stress test of the elbow is negative; UCL is intact.",
        "Tinel's sign is positive at the cubital tunnel, reproducing tingling in digits 4-5.",
        "Elbow flexion is measured at 125 degrees on the right (normal 145 degrees).",
        "Elbow extension is full at 0 degrees bilaterally.",
        "Forearm supination is measured at 70 degrees (normal 85 degrees).",
        "Forearm pronation is measured at 65 degrees (normal 75 degrees).",
        "Grip strength is reduced on the right, measuring 28 kg versus 45 kg on the left.",
        "No joint effusion or olecranon bursitis is noted.",
        "Chair test is positive on the right, reproducing lateral elbow pain with lifting.",
    ],
    "ankle_foot": [
        "Anterior drawer test of the right ankle is positive with 8mm translation, suggesting ATFL laxity.",
        "Anterior drawer test is negative bilaterally; anterior talofibular ligament is intact.",
        "Talar tilt test is negative bilaterally; calcaneofibular ligament is intact.",
        "Thompson's test is negative; Achilles tendon is intact.",
        "Tenderness is noted over the lateral malleolus and ATFL on the right.",
        "Medial malleolus is non-tender; deltoid ligament complex is intact.",
        "Ankle dorsiflexion is measured at 10 degrees on the right (normal 20 degrees).",
        "Ankle plantarflexion is measured at 35 degrees on the right (normal 50 degrees).",
        "Subtalar inversion is measured at 20 degrees (normal 35 degrees).",
        "Subtalar eversion is measured at 10 degrees (normal 15 degrees).",
        "Mild edema is noted around the right lateral malleolus.",
        "No ecchymosis is present; acute injury signs have resolved.",
        "Gait analysis reveals the patient avoids full weight-bearing push-off on the right.",
        "Windlass test is positive, suggesting plantar fasciitis.",
        "Achilles tendon is tender to palpation 2-4 cm proximal to insertion.",
        "Mulder's click is negative; no interdigital neuroma suspected.",
        "Posterior tibial tendon function is intact with single-leg heel rise test.",
    ],
}

PSYCHIATRIC_EXAM: dict[str, list[str]] = {
    "mental_status_exam": [
        "The patient is alert and oriented to person, place, time, and situation.",
        "The patient appears well-groomed and appropriately dressed for the evaluation.",
        "The patient appears disheveled with poor grooming and hygiene, consistent with reported functional decline.",
        "Eye contact is fair but intermittent; the patient avoids sustained eye contact.",
        "Eye contact is good throughout the interview; the patient is cooperative and engaged.",
        "Speech is normal in rate, rhythm, and volume.",
        "Speech is slow and deliberate with increased latency of response.",
        "Speech is pressured at times when discussing work-related stressors.",
        "Psychomotor activity is within normal limits; no agitation or retardation observed.",
        "Mild psychomotor retardation is noted, consistent with depressive symptomatology.",
    ],
    "appearance_behavior": [
        "The patient appears older than stated age, consistent with chronic pain and sleep disruption.",
        "The patient is cooperative with the examination but appears anxious and hypervigilant.",
        "The patient becomes tearful when discussing the workplace injury and its aftermath.",
        "Behavioral observations reveal frequent position shifting and wincing, consistent with pain complaints.",
        "The patient demonstrates restricted emotional range, appearing flat and withdrawn.",
        "The patient is guarded but provides adequate history with appropriate prompting.",
        "Motor behavior reveals hand-wringing and restlessness throughout the interview.",
        "The patient startles easily to unexpected sounds during the evaluation.",
    ],
    "mood_affect": [
        "Mood is described as 'depressed' and 'anxious most of the time.'",
        "Mood is described as 'irritable and frustrated' with feelings of hopelessness.",
        "Affect is constricted, ranging from sad to anxious with no spontaneous positive affect.",
        "Affect is labile, with the patient becoming tearful when discussing the injury and its impact on daily functioning.",
        "Affect is blunted with diminished emotional reactivity.",
        "Affect is mood-congruent and appropriate to content of discussion.",
        "The patient reports persistent anhedonia, stating 'nothing is enjoyable anymore.'",
        "The patient denies active suicidal ideation but endorses passive death wishes, stating 'sometimes I just wish I wouldn't wake up.'",
        "The patient denies suicidal ideation, homicidal ideation, and intent to harm self or others.",
        "Mood is described as 'anxious and on edge' with difficulty relaxing.",
    ],
    "thought_process": [
        "Thought process is logical, linear, and goal-directed throughout the evaluation.",
        "Thought process is tangential at times, requiring redirection to the topic at hand.",
        "Thought process is circumstantial with excessive detail but eventually reaches the point.",
        "No evidence of loose associations, flight of ideas, or thought blocking.",
        "Thought content is notable for rumination about the workplace injury and its consequences.",
        "The patient denies auditory or visual hallucinations.",
        "The patient endorses intrusive, distressing memories of the workplace incident occurring daily.",
        "No paranoid ideation or delusions are elicited.",
        "The patient demonstrates catastrophic thinking patterns regarding future employment prospects.",
        "Thought content includes persistent worry about financial stability and ability to provide for family.",
    ],
    "cognition": [
        "Attention and concentration are mildly impaired; the patient has difficulty with serial 7s, completing only 3 before losing track.",
        "Attention and concentration are grossly intact; the patient completes serial 7s and digit span within normal limits.",
        "Immediate recall is intact for 3 out of 3 objects; delayed recall is 2 out of 3 at 5 minutes.",
        "Delayed recall is impaired at 1 out of 3 objects at 5 minutes, consistent with attention/concentration difficulties.",
        "Fund of knowledge is average and consistent with stated educational background.",
        "Abstract reasoning is intact, as demonstrated by proverb interpretation and similarities.",
        "Judgment is fair; the patient demonstrates adequate understanding of consequences.",
        "Insight is limited regarding the psychological components of the chronic pain syndrome.",
        "Insight is fair; the patient recognizes the need for psychiatric treatment.",
    ],
    "psychological_testing": [
        "The MMPI-2 validity scales suggest a valid profile with no evidence of over-reporting or under-reporting of symptoms.",
        "MMPI-2 results reveal clinically significant elevations on Scales 1 (Hs), 2 (D), and 7 (Pt), consistent with somatic preoccupation, depression, and anxiety.",
        "MMPI-2 F scale is moderately elevated, consistent with genuine distress rather than symptom exaggeration.",
        "The Beck Depression Inventory-II (BDI-II) score is 28 out of 63, indicating moderate depression.",
        "The BDI-II score is 38 out of 63, indicating severe depression.",
        "The Patient Health Questionnaire-9 (PHQ-9) score is 18 out of 27, indicating moderately severe depression.",
        "The PHQ-9 score is 22 out of 27, indicating severe depression.",
        "The PCL-5 (PTSD Checklist) score is 52 out of 80, meeting the clinical cutoff for probable PTSD (cutoff: 33).",
        "The Beck Anxiety Inventory (BAI) score is 26 out of 63, indicating moderate anxiety.",
        "The BAI score is 35 out of 63, indicating severe anxiety.",
        "Symptom validity testing with the TOMM reveals scores above the cutoff on both trials, consistent with adequate effort.",
        "Forced-choice testing results are consistent with adequate effort and valid symptom reporting.",
    ],
    "dsm5_criteria": [
        "The patient meets DSM-5 criteria for Major Depressive Disorder, Single Episode, Moderate (F32.1), with depressed mood, anhedonia, insomnia, fatigue, diminished concentration, and feelings of worthlessness.",
        "The patient meets DSM-5 criteria for Generalized Anxiety Disorder (F41.1) with excessive worry, restlessness, fatigue, difficulty concentrating, irritability, and sleep disturbance.",
        "The patient meets DSM-5 criteria for Post-Traumatic Stress Disorder (F43.10) with intrusive recollections, avoidance of trauma-related stimuli, negative alterations in cognition and mood, and marked alterations in arousal and reactivity.",
        "The patient meets DSM-5 criteria for Adjustment Disorder with Mixed Anxiety and Depressed Mood (F43.23), arising in the context of the industrial injury.",
        "The patient meets DSM-5 criteria for Somatic Symptom Disorder with Predominant Pain (F45.1) with excessive thoughts and behaviors related to somatic symptoms.",
        "The patient does not meet full DSM-5 criteria for PTSD; however, subclinical PTSD symptoms are present.",
        "Differential diagnosis includes Major Depressive Disorder versus Adjustment Disorder; duration and severity favor MDD diagnosis.",
    ],
    "gaf_assessment": [
        "Global Assessment of Functioning (GAF) is estimated at 45 (serious symptoms — serious impairment in social, occupational, and daily functioning).",
        "GAF is estimated at 50 (serious symptoms — moderate difficulty in social and occupational functioning).",
        "GAF is estimated at 55 (moderate symptoms — moderate difficulty in social, occupational, or school functioning).",
        "GAF is estimated at 48 (serious symptoms — inability to maintain employment, few friends, conflict with family).",
        "GAF is estimated at 58 (moderate symptoms — moderate difficulty with work attendance and social engagement).",
        "Pre-injury GAF is estimated at 75-80 (no more than slight impairment in functioning).",
        "Current GAF represents a significant decline from estimated pre-injury baseline of 78.",
        "The GARF (Global Assessment of Relational Functioning) is estimated at 45, reflecting serious disruption in family relationships since the injury.",
    ],
    "functional_assessment": [
        "The patient reports significant impairment in activities of daily living, requiring assistance with household chores, meal preparation, and personal hygiene on some days.",
        "The patient is unable to maintain regular work attendance due to anxiety symptoms, concentration difficulties, and fatigue.",
        "Social functioning is markedly impaired; the patient has withdrawn from friends and family and avoids social gatherings.",
        "The patient reports inability to drive on freeways due to anxiety and panic symptoms.",
        "Sleep is severely disrupted with initial insomnia (2-3 hours to fall asleep), middle insomnia (3-4 awakenings per night), and nightmares related to the workplace incident.",
        "The patient reports being able to perform only limited household tasks before becoming fatigued or overwhelmed by pain and anxiety.",
        "Concentration difficulties prevent the patient from reading, watching television, or managing personal finances for extended periods.",
        "The patient avoids the area near the workplace and experiences significant distress when encountering reminders of the incident.",
    ],
}

NEUROLOGY_EXAM: dict[str, list[str]] = {
    "cranial_nerves": [
        "Cranial nerve II: Visual fields are full to confrontation bilaterally; fundoscopic exam reveals sharp disc margins.",
        "Cranial nerves III, IV, VI: Extraocular movements are intact without nystagmus or diplopia.",
        "Cranial nerve V: Facial sensation is intact to light touch and pinprick in all three divisions bilaterally.",
        "Cranial nerve VII: Facial symmetry is maintained with intact forehead wrinkling, eye closure, and smile.",
        "Cranial nerve VIII: Hearing is grossly intact to finger rub bilaterally; Weber test is midline.",
        "Cranial nerves IX, X: Palate elevates symmetrically; gag reflex is intact bilaterally.",
        "Cranial nerve XI: Sternocleidomastoid and trapezius strength is 5/5 bilaterally.",
        "Cranial nerve XII: Tongue protrudes midline without fasciculations or atrophy.",
        "Pupillary reflexes are equal and reactive to light and accommodation, 3mm bilaterally.",
        "Cranial nerve I: Olfaction is intact to coffee and vanilla testing bilaterally.",
    ],
    "motor_exam": [
        "Motor examination reveals 5/5 strength in all major muscle groups of the upper and lower extremities bilaterally.",
        "Right deltoid strength is 4/5 (C5); right biceps is 4+/5 (C5-C6).",
        "Left tibialis anterior is 4/5 (L4); left extensor hallucis longus is 4-/5 (L5).",
        "Bilateral grip strength is reduced: right 30 kg, left 35 kg (expected >40 kg for age/sex).",
        "No pronator drift is observed with arms outstretched and eyes closed for 20 seconds.",
        "Pronator drift is noted on the right, subtle but reproducible.",
        "Muscle tone is normal throughout; no spasticity, rigidity, or hypotonia.",
        "Mild increased tone is noted in the right upper extremity, velocity-dependent, consistent with mild spasticity.",
        "No fasciculations or atrophy are observed in any muscle groups.",
        "Mild atrophy of the right thenar eminence is noted, consistent with chronic median neuropathy.",
        "Muscle bulk is symmetric bilaterally in upper and lower extremities.",
    ],
    "sensory_exam": [
        "Light touch sensation is intact and symmetric in all dermatomes tested (C5-T1, L2-S1).",
        "Light touch is diminished in the C6 dermatome on the right (lateral forearm and thumb).",
        "Pinprick sensation is diminished in the L5 dermatome on the left (lateral leg and dorsal foot).",
        "Vibration sense is intact at the bilateral great toes and medial malleoli.",
        "Vibration sense is diminished at the right great toe (8 seconds versus 15 seconds on the left).",
        "Proprioception is intact at the bilateral great toes.",
        "Temperature discrimination is intact bilaterally in upper and lower extremities.",
        "Stocking-glove pattern of sensory loss is not present; no peripheral neuropathy pattern.",
        "A non-dermatomal pattern of sensory change is noted in the right lower extremity, inconsistent with radiculopathy.",
        "Romberg test is negative; proprioceptive function is intact.",
    ],
    "reflex_exam": [
        "Deep tendon reflexes are 2+ and symmetric at the biceps (C5-C6), triceps (C7), brachioradialis (C5-C6), patellar (L3-L4), and Achilles (S1) bilaterally.",
        "Right biceps reflex is 1+ (C5-C6), diminished compared to 2+ on the left.",
        "Left Achilles reflex is 1+ (S1), diminished compared to 2+ on the right.",
        "Patellar reflexes are 3+ bilaterally, brisk but without clonus.",
        "Plantar responses are flexor (downgoing) bilaterally; Babinski sign is absent.",
        "Babinski sign is absent bilaterally; no upper motor neuron signs.",
        "Hoffmann's sign is absent bilaterally.",
        "Clonus is absent at the ankles bilaterally.",
        "Jaw jerk reflex is normal (1+).",
    ],
    "coordination": [
        "Finger-to-nose testing is performed accurately without dysmetria or intention tremor bilaterally.",
        "Rapid alternating movements (diadochokinesia) are performed smoothly bilaterally.",
        "Heel-to-shin testing is performed accurately bilaterally without ataxia.",
        "Tandem gait is performed without difficulty for 10 steps.",
        "Tandem gait reveals mild unsteadiness but is performed without assistance.",
        "Romberg test is negative; no significant sway with eyes closed.",
        "No resting or action tremor is observed.",
    ],
    "emg_ncv": [
        "Electromyography (EMG) of the right upper extremity reveals fibrillation potentials and positive sharp waves in the C6-innervated muscles, consistent with active C6 radiculopathy.",
        "Nerve conduction studies reveal prolonged distal motor latency of the right median nerve (5.2 ms, normal <4.4 ms), consistent with carpal tunnel syndrome.",
        "Right median sensory nerve conduction velocity across the wrist is 38 m/s (normal >50 m/s), consistent with moderate carpal tunnel syndrome.",
        "EMG of the left lower extremity reveals chronic denervation changes (large-amplitude, long-duration MUAPs) in L5-innervated muscles, consistent with chronic L5 radiculopathy.",
        "Nerve conduction studies of the bilateral lower extremities are within normal limits; no evidence of peripheral neuropathy.",
        "EMG reveals no evidence of acute or chronic denervation in the tested muscles.",
        "Right ulnar motor nerve conduction velocity across the elbow is 42 m/s (normal >50 m/s), consistent with ulnar neuropathy at the elbow.",
        "F-wave latencies are within normal limits bilaterally.",
        "H-reflex is absent on the left (S1), consistent with left S1 radiculopathy.",
    ],
}

PAIN_MANAGEMENT_EXAM: dict[str, list[str]] = {
    "pain_assessment": [
        "The patient rates current pain at 7/10 on the Numeric Pain Rating Scale (NRS), with worst pain at 9/10 and best pain at 4/10.",
        "Pain is described as constant, dull, and aching with intermittent sharp, stabbing exacerbations.",
        "Pain is localized primarily to the low back with radiation into the left posterior thigh and calf.",
        "Pain is described as burning and electric in quality, consistent with neuropathic component.",
        "The patient reports that pain is worse with prolonged sitting, standing, bending, and lifting.",
        "Pain is partially relieved by rest, ice, and prescribed medications but never fully resolves.",
        "The patient reports nighttime pain that disrupts sleep, requiring repositioning every 1-2 hours.",
        "Visual Analog Scale (VAS) pain score is 72 mm out of 100 mm.",
        "The Oswestry Disability Index score is 54%, indicating severe disability.",
        "The Oswestry Disability Index score is 38%, indicating moderate disability.",
        "Pain diagram reveals markings consistent with the reported body parts with no non-anatomical distribution.",
        "The patient demonstrates pain behaviors including guarding, grimacing, and bracing during positional changes.",
        "DN4 (Douleur Neuropathique 4) questionnaire score is 5 out of 10, confirming neuropathic pain component.",
        "The Pain Catastrophizing Scale reveals a score of 35 out of 52, indicating significant pain catastrophizing.",
    ],
    "functional_assessment": [
        "The patient reports being able to sit for 20-30 minutes before needing to change position.",
        "Standing tolerance is reported at 15-20 minutes before pain becomes severe.",
        "Walking distance is limited to approximately 1-2 blocks before requiring rest.",
        "The patient reports inability to perform household chores including vacuuming, mopping, and yard work.",
        "Lifting capacity is self-reported at 5-10 pounds maximum.",
        "The patient requires assistance with activities of daily living including bathing, dressing, and meal preparation on high-pain days.",
        "Sleep is significantly disrupted with the patient averaging 3-4 hours of fragmented sleep per night.",
        "The patient reports that pain interferes with concentration, reading, and watching television.",
        "Driving is limited to short distances (15-20 minutes) due to pain with prolonged sitting.",
        "The patient has discontinued all recreational activities including walking, gardening, and social events.",
        "Functional Capacity Evaluation (FCE) places the patient in the sedentary to light physical demand level.",
    ],
    "medication_review": [
        "Current pain medication regimen includes gabapentin 600mg TID, meloxicam 15mg daily, and cyclobenzaprine 10mg at bedtime.",
        "The patient has failed trials of NSAIDs (ibuprofen, naproxen), muscle relaxants (methocarbamol), and topical diclofenac.",
        "Current opioid regimen consists of tramadol 50mg every 6 hours as needed, with the patient using 3-4 doses daily.",
        "The patient's morphine milligram equivalent (MME) is 60 MME/day, within the MTUS recommended threshold of <90 MME/day.",
        "Current MME is 40 MME/day; patient reports partial relief with current regimen.",
        "The patient reports approximately 30% pain relief with current medication regimen.",
        "Gabapentin has been titrated to 800mg TID with moderate improvement in neuropathic symptoms.",
        "Pregabalin 75mg BID was substituted for gabapentin due to dizziness side effects, with improved tolerability.",
        "The patient reports side effects of drowsiness and dizziness from gabapentin but tolerates current dose.",
        "Duloxetine 60mg daily was added for combined depression and neuropathic pain management with good effect.",
        "Opioid risk screening (ORT) score is 3, indicating low risk for opioid misuse.",
        "The CURES (Controlled Substance Utilization Review and Evaluation System) report is reviewed and consistent with prescribed medications.",
    ],
    "intervention_history": [
        "The patient has received three lumbar epidural steroid injections (L4-L5 and L5-S1) with 40-50% temporary relief lasting 4-6 weeks each.",
        "The patient underwent a medial branch block at L3-L4 and L4-L5 bilaterally with >80% relief, qualifying for radiofrequency ablation.",
        "Radiofrequency ablation of the L3-L5 medial branches was performed with 70% sustained relief for approximately 8 months.",
        "Trigger point injections to the bilateral trapezius and levator scapulae provided temporary relief of 2-3 weeks.",
        "The patient has undergone a total of 6 epidural steroid injections over the course of treatment.",
        "Cervical epidural steroid injection at C5-C6 provided minimal relief (<25%), and repeat injection is not recommended.",
        "A spinal cord stimulator trial was performed over 7 days with 60% pain relief, meeting criteria for permanent implantation.",
        "The patient has not yet undergone any interventional pain procedures and is being considered for initial epidural steroid injection.",
        "Sacroiliac joint injection with corticosteroid provided >75% relief, confirming the SI joint as a pain generator.",
        "Genicular nerve block of the right knee was performed with 70% relief, supporting consideration for radiofrequency ablation.",
    ],
}

# ---------------------------------------------------------------------------
# ROM Normal Values (for generating measured-vs-normal tables)
# ---------------------------------------------------------------------------

ROM_NORMAL_VALUES: dict[str, dict[str, tuple[str, int]]] = {
    "cervical spine": {
        "flexion": ("Flexion", 80),
        "extension": ("Extension", 50),
        "right_lateral_flexion": ("Right Lateral Flexion", 45),
        "left_lateral_flexion": ("Left Lateral Flexion", 45),
        "right_rotation": ("Right Rotation", 80),
        "left_rotation": ("Left Rotation", 80),
    },
    "lumbar spine": {
        "flexion": ("Flexion", 60),
        "extension": ("Extension", 25),
        "right_lateral_flexion": ("Right Lateral Flexion", 25),
        "left_lateral_flexion": ("Left Lateral Flexion", 25),
        "right_rotation": ("Right Rotation", 30),
        "left_rotation": ("Left Rotation", 30),
    },
    "shoulder": {
        "flexion": ("Forward Flexion", 180),
        "abduction": ("Abduction", 180),
        "internal_rotation": ("Internal Rotation", 80),
        "external_rotation": ("External Rotation", 90),
        "extension": ("Extension", 60),
        "adduction": ("Adduction", 45),
    },
    "knee": {
        "flexion": ("Flexion", 135),
        "extension": ("Extension", 0),
    },
    "hip": {
        "flexion": ("Flexion", 120),
        "extension": ("Extension", 30),
        "abduction": ("Abduction", 45),
        "adduction": ("Adduction", 30),
        "internal_rotation": ("Internal Rotation", 40),
        "external_rotation": ("External Rotation", 45),
    },
    "wrist": {
        "flexion": ("Flexion", 80),
        "extension": ("Extension", 70),
        "radial_deviation": ("Radial Deviation", 20),
        "ulnar_deviation": ("Ulnar Deviation", 30),
        "supination": ("Supination", 85),
        "pronation": ("Pronation", 75),
    },
    "elbow": {
        "flexion": ("Flexion", 145),
        "extension": ("Extension", 0),
        "supination": ("Supination", 85),
        "pronation": ("Pronation", 75),
    },
    "ankle": {
        "dorsiflexion": ("Dorsiflexion", 20),
        "plantarflexion": ("Plantarflexion", 50),
        "inversion": ("Inversion", 35),
        "eversion": ("Eversion", 15),
    },
}

# ---------------------------------------------------------------------------
# Clinical Rationale Pools
# ---------------------------------------------------------------------------

UR_CLINICAL_RATIONALE: dict[str, list[str]] = {
    "approved": [
        "The requested treatment is consistent with MTUS guidelines (8 CCR §9792.24.2) for the documented condition and stage of recovery.",
        "Medical records demonstrate that the patient has failed conservative treatment measures including physical therapy and NSAIDs, supporting escalation of care.",
        "The ACOEM Practice Guidelines support the requested intervention for patients with the documented clinical presentation.",
        "Diagnostic imaging confirms structural pathology consistent with the patient's symptoms, supporting the medical necessity of the requested procedure.",
        "The patient's clinical presentation meets the criteria outlined in MTUS for the requested treatment modality.",
        "Peer-reviewed literature supports the efficacy of the requested treatment for the documented diagnosis (Level I-II evidence).",
        "The treating physician has provided adequate documentation of failed conservative measures per MTUS requirements.",
        "The request is within the MTUS-recommended frequency and duration for this treatment modality.",
        "The patient's functional status and pain levels support the medical necessity of continued treatment.",
        "The requested procedure is appropriate given the chronicity of symptoms and failure of conservative management.",
        "Review of the submitted medical records confirms that the treatment plan is evidence-based and medically indicated.",
        "The treatment request is consistent with the ACOEM Chronic Pain chapter recommendations for the patient's condition.",
    ],
    "denied": [
        "The requested treatment does not meet MTUS guidelines (8 CCR §9792.24.2) for the documented condition at this stage of recovery.",
        "Insufficient documentation has been provided to establish medical necessity per MTUS requirements.",
        "The patient has not demonstrated adequate trial of conservative treatment measures as required by MTUS before escalation to the requested intervention.",
        "The ACOEM Practice Guidelines do not support the requested treatment frequency for the documented condition.",
        "Diagnostic studies do not demonstrate structural pathology that would respond to the requested treatment.",
        "The peer-reviewed literature does not support the efficacy of the requested treatment for the documented diagnosis.",
        "The requested treatment exceeds the MTUS-recommended frequency or duration for this modality without documented justification.",
        "The medical records do not demonstrate measurable functional improvement with prior treatments of the same type.",
        "Alternative, less invasive treatment options that are supported by evidence-based guidelines have not been adequately explored.",
        "The requested procedure is not medically indicated based on the current clinical presentation and objective findings.",
        "The clinical documentation does not support a change in treatment plan at this time; continuation of current conservative measures is recommended.",
        "The MTUS guidelines recommend a minimum 6-week trial of physical therapy before the requested intervention, which has not been completed.",
    ],
    "modified": [
        "The requested treatment is partially approved with modification to align with MTUS guidelines for frequency and duration.",
        "The treatment is approved for a reduced number of sessions (initial 6 sessions) with re-evaluation before continuation.",
        "The requested imaging is modified from MRI with contrast to MRI without contrast, as contrast is not medically indicated per MTUS.",
        "The requested frequency of 3 times per week is modified to 2 times per week, consistent with MTUS guidelines for this stage of recovery.",
        "The treatment is approved with the modification that a formal re-evaluation must be performed after 4 weeks to document functional progress.",
        "The requested medication is approved at a lower starting dose per MTUS opioid guidelines, with titration based on documented response.",
        "The procedure is approved on a trial basis; continuation will require documentation of measurable functional improvement.",
        "The treatment plan is modified to include concurrent active rehabilitation per MTUS guidelines for multimodal care.",
    ],
}

MTUS_GUIDELINE_CITATIONS: dict[str, list[str]] = {
    "spine_conservative": [
        "MTUS Chronic Pain Medical Treatment Guidelines (8 CCR §9792.24.2), Section: Low Back Complaints — Conservative Treatment",
        "ACOEM Practice Guidelines: Low Back Disorders, Chapter 7 — Recommendations for Activity Modification and Physical Therapy",
        "MTUS: Cervical and Thoracic Spine Disorders — Conservative Management Pathway (8 CCR §9792.24.2)",
        "ACOEM Cervical and Thoracic Spine Disorders Chapter — Recommendation: Initial trial of 6-8 weeks active physical therapy",
        "MTUS Chronic Pain Guidelines — Recommendation: Multimodal treatment approach incorporating cognitive behavioral therapy",
    ],
    "spine_surgical": [
        "MTUS Chronic Pain Guidelines — Surgical Indications: Progressive neurological deficit or cauda equina syndrome",
        "ACOEM Low Back Disorders Chapter — Recommendation: Surgical consideration after 6-12 months failed conservative treatment with confirmed structural pathology",
        "MTUS: Lumbar Fusion Criteria — Requires documented instability on flexion-extension radiographs or positive response to diagnostic facet blocks",
        "ACOEM Practice Guidelines — Recommendation: Discectomy for confirmed disc herniation with concordant radiculopathy unresponsive to 6-8 weeks conservative care",
    ],
    "upper_extremity": [
        "MTUS Upper Extremity Medical Treatment Guidelines (8 CCR §9792.24.2) — Carpal Tunnel Syndrome Treatment Algorithm",
        "ACOEM Practice Guidelines: Elbow Disorders — Lateral Epicondylitis Conservative Management Pathway",
        "MTUS: Shoulder Disorders — Recommendation: 6-12 weeks physical therapy before surgical consideration for rotator cuff tears <3cm",
        "ACOEM: Hand, Wrist, and Forearm Disorders — Recommendation: Night splinting for 4-6 weeks as initial CTS treatment",
        "MTUS Upper Extremity Guidelines — Injection Therapy: Maximum 3 corticosteroid injections to same site per 12 months",
    ],
    "opioid_guidelines": [
        "MTUS Opioid Treatment Guidelines (8 CCR §9792.24.4) — Recommendation: Limit to <90 MME/day; >50 MME/day requires documented justification",
        "ACOEM Chronic Pain Guidelines — Recommendation: Opioids are not first-line treatment for chronic non-cancer pain",
        "MTUS Opioid Guidelines — Requirement: CURES report review before prescribing or continuing opioid therapy",
        "MTUS: Opioid tapering protocol when patient at >90 MME/day without documented functional improvement",
        "ACOEM Chronic Pain Chapter — Recommendation: Urine drug testing at baseline and periodically during opioid therapy",
    ],
    "physical_therapy": [
        "MTUS Chronic Pain Guidelines — Physical Therapy: Initial authorization of 12-24 visits over 8-12 weeks with documented functional goals",
        "ACOEM Practice Guidelines — Recommendation: Active over passive treatment modalities for chronic musculoskeletal conditions",
        "MTUS: Physical Therapy continuation requires documented measurable functional improvement at 6-week intervals",
        "ACOEM: Aquatic therapy recommendation for patients unable to tolerate land-based exercise due to weight-bearing limitations",
    ],
    "injection_therapy": [
        "MTUS Chronic Pain Guidelines — Epidural Steroid Injections: Maximum 4 per year for same spinal level with documented >50% relief lasting >4 weeks",
        "ACOEM Practice Guidelines — Recommendation: Fluoroscopically-guided injections for diagnostic and therapeutic accuracy",
        "MTUS: Facet Joint Interventions — Medial branch blocks required before radiofrequency ablation with >80% relief on 2 separate occasions",
        "MTUS: Trigger Point Injections — Limited to 4 sessions without documented functional improvement",
        "ACOEM Chronic Pain Chapter — Recommendation: Diagnostic injections should provide >80% concordant relief to confirm pain generator",
    ],
}

# ---------------------------------------------------------------------------
# Record Review Items
# ---------------------------------------------------------------------------

RECORD_REVIEW_ITEMS: list[str] = [
    "Emergency department records, initial evaluation and treatment",
    "Ambulance/transport records",
    "Primary treating physician progress notes",
    "Orthopedic consultation notes",
    "Physical therapy evaluation and progress notes",
    "Physical therapy discharge summary",
    "MRI report — {body_part}",
    "X-ray reports — {body_part}",
    "CT scan report — {body_part}",
    "EMG/nerve conduction study report",
    "Operative report",
    "Post-operative progress notes",
    "Anesthesia records",
    "Discharge summary — hospital",
    "Pharmacy records and medication log",
    "Utilization review decision letters",
    "IMR determination letter",
    "DWC-1 Workers' Compensation Claim Form",
    "Employer's First Report of Occupational Injury (Form 5020)",
    "Employer's initial medical treatment authorization",
    "Job description — {position}",
    "Wage statement — pre-injury earnings",
    "Temporary disability payment records",
    "Return-to-work/modified duty documentation",
    "Functional capacity evaluation report",
    "Pain management consultation notes",
    "Psychiatric/psychological evaluation",
    "Chiropractic treatment records",
    "Acupuncture treatment records",
    "Prior medical records — pre-injury {body_part} complaints",
    "Workers' compensation panel request and assignment",
    "Defense medical evaluation report",
    "Surveillance video summary (if applicable)",
    "Second opinion consultation records",
    "Medical-legal correspondence",
    "Diagnostic imaging CD/films reviewed",
    "Blood work and laboratory results",
    "Work restriction documentation",
    "Supplemental report(s) from treating physician",
    "Request for Authorization (RFA) forms",
    "Peer-to-peer consultation notes",
    "Physical medicine and rehabilitation consultation",
    "Neurosurgical consultation",
    "Pain questionnaires and outcome measures",
    "Sleep study (polysomnography) results",
]

# ---------------------------------------------------------------------------
# Treatment Narratives
# ---------------------------------------------------------------------------

TREATMENT_NARRATIVES: dict[str, list[str]] = {
    "conservative": [
        "Patient has been managed conservatively with rest, ice, compression, and elevation during the acute phase.",
        "Conservative treatment has included activity modification, ergonomic adjustments, and home exercise program.",
        "An initial trial of rest and over-the-counter NSAIDs was prescribed with instructions for gradual return to activity.",
        "Bracing and activity modification were implemented for the first 6 weeks following injury.",
        "Conservative management included a structured physical therapy program with modalities and therapeutic exercises.",
        "Topical treatments including diclofenac gel and lidocaine patches have been utilized for localized pain relief.",
        "A TENS unit was prescribed for home use, providing partial symptomatic relief.",
        "Conservative treatment was initiated per MTUS guidelines with NSAIDs, muscle relaxants, and physical therapy.",
        "The patient was placed on modified duty with work restrictions while undergoing conservative management.",
        "A home exercise program was prescribed and the patient reports compliance with stretching and strengthening exercises.",
    ],
    "interventional": [
        "The patient has undergone a series of epidural steroid injections with moderate temporary relief.",
        "Fluoroscopically-guided lumbar transforaminal epidural steroid injection was performed at L5-S1 on the left.",
        "Medial branch blocks were performed at L3-L4 and L4-L5 bilaterally as a diagnostic step prior to radiofrequency ablation.",
        "Trigger point injections were administered to the bilateral trapezius and cervical paraspinal muscles.",
        "Sacroiliac joint injection was performed under fluoroscopic guidance with corticosteroid and anesthetic.",
        "Platelet-rich plasma (PRP) injection was administered to the right supraspinatus tendon insertion.",
        "A series of three viscosupplementation injections (hyaluronic acid) was administered to the right knee.",
        "Genicular nerve block was performed at the right knee for diagnostic purposes prior to ablation consideration.",
        "Cervical medial branch radiofrequency ablation was performed at C3-C6 bilaterally.",
        "Lumbar radiofrequency ablation provided sustained relief for approximately 8 months before symptom recurrence.",
    ],
    "surgical": [
        "The patient underwent lumbar microdiscectomy at L4-L5 on the left with intraoperative confirmation of disc herniation.",
        "Arthroscopic rotator cuff repair of the right shoulder was performed with subacromial decompression.",
        "Anterior cervical discectomy and fusion (ACDF) was performed at C5-C6 with autograft and anterior plate fixation.",
        "Right knee arthroscopy with medial meniscectomy was performed, revealing a complex tear of the posterior horn.",
        "Carpal tunnel release surgery was performed on the right wrist using open technique.",
        "The patient underwent right shoulder arthroscopy with labral debridement and subacromial decompression.",
        "Lumbar laminectomy at L4-L5 was performed for central canal stenosis with neurogenic claudication.",
        "Total knee arthroplasty (right) was performed due to post-traumatic arthritis.",
        "Ulnar nerve transposition at the right elbow was performed for cubital tunnel syndrome.",
        "Post-surgical recovery has been complicated by persistent pain and limited range of motion despite adherence to rehabilitation protocol.",
    ],
    "medication_management": [
        "The patient's medication regimen has been adjusted multiple times to optimize pain control while minimizing side effects.",
        "NSAIDs were discontinued due to gastrointestinal side effects; the patient was transitioned to a COX-2 selective inhibitor.",
        "Gabapentin was titrated from 300mg daily to 600mg TID over 4 weeks with improvement in neuropathic symptoms.",
        "The patient was started on duloxetine 30mg daily, titrated to 60mg daily, for concurrent depression and neuropathic pain.",
        "Opioid therapy has been maintained at a stable dose below 50 MME/day with regular monitoring per MTUS guidelines.",
        "A trial of topiramate for pain was discontinued due to cognitive side effects.",
        "The patient's medications were reviewed and reconciled, with discontinuation of redundant NSAIDs.",
        "A formal opioid taper was initiated per MTUS guidelines, reducing the dose by 10% every 2 weeks.",
        "The addition of a muscle relaxant at bedtime improved the patient's sleep quality and morning stiffness.",
        "The patient's MME has been successfully reduced from 90 to 45 MME/day over 6 months without worsening of function.",
    ],
    "physical_therapy": [
        "Physical therapy has focused on core stabilization, flexibility, and progressive strengthening exercises.",
        "The patient has completed 18 sessions of physical therapy with documented improvement in range of motion.",
        "Aquatic therapy was initiated due to the patient's inability to tolerate land-based exercises.",
        "Physical therapy discharge summary indicates achievement of 80% of functional goals.",
        "The patient's physical therapy program includes McKenzie method exercises for directional preference.",
        "Work conditioning/work hardening program was initiated to prepare the patient for return to modified duty.",
        "Functional restoration program was recommended following plateau in standard physical therapy.",
        "The patient has been compliant with home exercise program as prescribed by physical therapy.",
        "Physical therapy has been supplemented with manual therapy techniques including joint mobilization and soft tissue work.",
        "Progress in physical therapy has plateaued after 8 weeks; re-evaluation of treatment plan is recommended.",
    ],
}

# ---------------------------------------------------------------------------
# Functional Capacity Descriptions
# ---------------------------------------------------------------------------

FUNCTIONAL_CAPACITY_DESCRIPTIONS: list[str] = [
    "The patient demonstrates the ability to perform at the sedentary physical demand level per the Dictionary of Occupational Titles.",
    "Functional capacity evaluation places the patient at the light physical demand level (lifting up to 20 lbs occasionally, 10 lbs frequently).",
    "The patient is unable to meet the physical demands of their pre-injury occupation, which requires medium to heavy physical demand level.",
    "Maximum occasional lifting capacity is measured at 15 pounds from floor to waist height.",
    "Maximum frequent lifting capacity is measured at 10 pounds from waist to shoulder height.",
    "The patient can sit for a maximum of 30 minutes continuously before requiring a position change.",
    "The patient can stand for a maximum of 20 minutes continuously before requiring a seated rest break.",
    "Walking tolerance is limited to 15-20 minutes on level surfaces; inclines and stairs increase symptoms significantly.",
    "The patient demonstrates the ability to perform sustained forward bending for up to 5 minutes.",
    "Overhead reaching is limited to brief (less than 30 seconds) intermittent tasks on the affected side.",
    "Grip strength is measured at 60% of expected normative values for age and sex on the affected side.",
    "The patient can push/pull up to 25 pounds of force on a horizontal plane.",
    "Climbing stairs is limited to one flight before requiring rest; the patient uses a handrail for support.",
    "The patient is unable to perform crawling, kneeling for extended periods, or squatting to full depth.",
    "Fine motor coordination is intact for tasks such as writing, keyboarding, and manipulating small objects.",
    "Sustained keyboarding is limited to 30 minutes per hour due to upper extremity symptoms.",
    "The patient demonstrates difficulty with sustained neck flexion beyond 20 minutes (relevant for desk work).",
    "Balance testing reveals mild instability on uneven surfaces; the patient should avoid ladders and scaffolding.",
    "The patient's endurance is reduced; sustained work activity beyond 4 hours produces significant symptom exacerbation.",
    "Carrying capacity is limited to 10 pounds for distances greater than 50 feet.",
    "The patient can drive for up to 30 minutes before lower extremity symptoms require a rest break.",
    "Bending and stooping frequency should be limited to occasional (up to 1/3 of the workday).",
    "The patient demonstrates functional limitations consistent with inability to return to pre-injury occupation.",
    "Modified duty within the sedentary to light physical demand level is feasible with accommodations.",
    "The patient's sustained work tolerance is 4-6 hours per day with regular rest breaks.",
]

# ---------------------------------------------------------------------------
# Future Medical Items
# ---------------------------------------------------------------------------

FUTURE_MEDICAL_ITEMS: dict[str, list[str]] = {
    "spine": [
        "Ongoing pain management including medication management every 4-8 weeks ($150-300 per visit)",
        "Annual epidural steroid injection series (up to 3 per year) at $1,500-3,000 per injection",
        "Radiofrequency ablation every 12-18 months at $3,500-5,000 per procedure",
        "Physical therapy flare-up protocol: 6-12 sessions per year at $150-200 per session",
        "Annual diagnostic imaging (MRI) to monitor for progression at $1,200-2,500 per study",
        "Continued medication management: gabapentin, NSAIDs, muscle relaxants (~$200-400/month)",
        "Lumbar fusion surgery if conservative measures fail ($75,000-150,000 including hospitalization)",
        "Spinal cord stimulator trial and implantation if indicated ($50,000-85,000)",
        "Home exercise equipment (TENS unit, exercise ball, resistance bands) — one-time $200-500",
        "Ergonomic workstation modifications for return to work ($500-2,000)",
    ],
    "upper_extremity": [
        "Ongoing orthopedic follow-up every 3-6 months ($150-300 per visit)",
        "Corticosteroid injection to affected joint up to 3 times per year ($500-1,500 per injection)",
        "Physical therapy maintenance: 12-24 sessions per year ($150-200 per session)",
        "Continued medication management: NSAIDs, topical analgesics (~$100-200/month)",
        "Repeat MRI or ultrasound as clinically indicated ($800-2,000 per study)",
        "Surgical revision if initial repair fails ($25,000-60,000)",
        "Custom orthotic/splinting with periodic replacement ($200-500 per device)",
        "Functional capacity evaluation annually to monitor work capacity ($1,500-3,000)",
        "Assistive devices for activities of daily living ($100-500)",
    ],
    "lower_extremity": [
        "Ongoing orthopedic follow-up every 3-6 months ($150-300 per visit)",
        "Viscosupplementation injections (hyaluronic acid) series annually ($1,500-3,000 per series)",
        "Physical therapy maintenance: 12-24 sessions per year ($150-200 per session)",
        "Custom orthotics and supportive footwear with annual replacement ($300-800/year)",
        "Annual diagnostic imaging to monitor for degenerative progression ($500-1,500)",
        "Total joint arthroplasty if conservative measures fail ($40,000-80,000 including rehab)",
        "Ambulatory aids (cane, knee brace) with periodic replacement ($100-500/year)",
        "Continued medication management: NSAIDs, topical analgesics (~$100-200/month)",
        "Home modifications (grab bars, shower chair) — one-time $500-2,000",
    ],
    "psyche": [
        "Ongoing psychiatric medication management every 4-8 weeks ($200-400 per visit)",
        "Individual psychotherapy (CBT/EMDR) weekly to biweekly ($150-250 per session)",
        "Psychiatric medication costs: antidepressants, anxiolytics (~$100-400/month)",
        "Annual psychological testing to monitor treatment progress ($1,500-3,000)",
        "Group therapy for chronic pain management ($50-100 per session, weekly)",
        "Psychiatric hospitalization for crisis stabilization if needed ($2,000-5,000/day)",
        "Medication management adjustments as clinically indicated",
        "Sleep study and ongoing sleep disorder treatment ($1,500-3,000 initial, $100-200/month ongoing)",
    ],
}

# ---------------------------------------------------------------------------
# Chronology Event Descriptions (varied per event type)
# ---------------------------------------------------------------------------

CHRONOLOGY_EVENT_DESCRIPTIONS: dict[str, list[str]] = {
    "initial_treatment": [
        "Initial emergency department evaluation. Chief complaint of acute pain following workplace incident. Physical examination performed, diagnostic imaging ordered. Pain medication prescribed.",
        "Urgent care evaluation following work injury. Examination reveals tenderness and restricted range of motion. X-rays obtained; no acute fracture identified. Patient placed on modified duty with pain medications.",
        "Initial evaluation at treating physician's office. Patient reports acute onset of symptoms following workplace incident. Comprehensive examination performed with documentation of objective findings.",
    ],
    "office_visit": [
        "Follow-up office visit. Patient reports ongoing symptoms with pain rated {pain}/10. Physical examination reveals persistent findings. Treatment plan adjusted; medications continued.",
        "Progress evaluation. Patient reports {progress} since last visit. Objective examination demonstrates {exam_finding}. Current treatment plan maintained with follow-up in {weeks} weeks.",
        "Routine follow-up visit. Symptoms are {symptom_status}. Physical examination findings are consistent with prior visits. Work restrictions continued.",
        "Re-evaluation appointment. Patient describes pain as {pain_quality} with functional limitations in {limitation}. Physical therapy progress discussed. Next follow-up scheduled.",
        "Follow-up examination. Patient reports partial improvement with current medication regimen. Objective findings demonstrate residual deficit. Work status reviewed and restrictions updated.",
    ],
    "physical_therapy": [
        "Physical therapy session #{session_num}. Treatment included therapeutic exercises, manual therapy, and modalities. Patient tolerated treatment well with gradual improvement in range of motion.",
        "PT evaluation and treatment. Objective measurements document {rom_change}. Functional goals updated. Home exercise program reviewed and progressed.",
        "Physical therapy visit. Focus on core stabilization and progressive strengthening. Patient reports decreased pain with exercises. Compliance with home program is good.",
        "Physical therapy session. Treatment included aquatic therapy for low-impact strengthening. Patient reports improved tolerance to exercise in water.",
        "PT session focused on work conditioning activities. Simulated job tasks performed with attention to proper body mechanics.",
    ],
    "diagnostic_imaging": [
        "MRI of {body_part} performed. Findings demonstrate {mri_finding}. Results correlate with clinical presentation. Report forwarded to treating physician for review.",
        "X-ray examination of {body_part} completed. Findings: {xray_finding}. No acute fracture or dislocation identified. Degenerative changes noted.",
        "CT scan of {body_part} obtained for further characterization of previously identified pathology. Results pending radiologist interpretation.",
        "Diagnostic ultrasound of {body_part} performed. Findings demonstrate {us_finding}. Correlated with clinical examination.",
    ],
    "specialist_consult": [
        "Orthopedic consultation. Specialist concurs with current treatment plan and recommends continuation of conservative management for {duration} before considering surgical options.",
        "Pain management consultation. New patient evaluation including comprehensive pain assessment. Treatment plan discussed including medication management and consideration for interventional procedures.",
        "Neurosurgical consultation for evaluation of {condition}. Review of imaging and clinical findings. Surgical intervention {surgical_rec} at this time.",
        "Second opinion evaluation by {specialty} specialist. Diagnostic findings reviewed. Treatment recommendations provided consistent with MTUS guidelines.",
    ],
    "injection": [
        "Fluoroscopically-guided epidural steroid injection performed at {level}. Patient tolerated procedure well. Post-procedure instructions provided including activity restrictions for 24-48 hours.",
        "Trigger point injection administered to {muscle_group}. Patient reports immediate relief of localized pain. Follow-up scheduled to assess duration of response.",
        "Diagnostic medial branch block performed at {levels}. Patient reports >80% relief, meeting criteria for radiofrequency ablation consideration.",
        "Corticosteroid injection to {joint} performed under ultrasound guidance. No complications. Patient to follow up in 2-4 weeks to assess response.",
    ],
    "surgery": [
        "Surgical procedure: {procedure}. Patient tolerated the procedure well; no intraoperative complications. Estimated blood loss was minimal. Patient transferred to recovery in stable condition.",
        "Operative procedure performed as planned. Intraoperative findings confirmed pre-operative diagnosis. Post-operative orders entered including pain management protocol and rehabilitation timeline.",
    ],
    "ur_dispute": [
        "Utilization review decision received. Requested treatment {ur_decision}. Treating physician disagrees with determination and is preparing appeal/IMR request.",
        "IMR determination letter received. The UR decision was {imr_outcome}. {imr_followup}",
        "Request for Authorization (RFA) submitted for {treatment}. UR decision pending. Treatment cannot proceed until authorization is obtained.",
    ],
    "medication_change": [
        "Medication adjustment. {old_med} discontinued due to {reason}. Started {new_med} with instructions for titration schedule. Follow-up for efficacy assessment in {weeks} weeks.",
        "Pain medication management visit. Current regimen reviewed and optimized. Total daily MME is {mme} MME/day. CURES report reviewed; consistent with prescribed medications.",
        "Medication refill visit. Patient reports stable pain control with current regimen. No adverse effects reported. Prescriptions renewed for {duration}.",
    ],
}

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

_SPECIALTY_TO_EXAM_MAP = {
    "Orthopedic Surgery": ORTHOPEDIC_EXAM,
    "Hand Surgery": ORTHOPEDIC_EXAM,
    "Neurosurgery": ORTHOPEDIC_EXAM,  # uses same physical exam approach
    "Physical Medicine & Rehabilitation (PM&R)": ORTHOPEDIC_EXAM,
    "Chiropractic": ORTHOPEDIC_EXAM,
    "Physical Therapy": ORTHOPEDIC_EXAM,
    "Psychiatry": PSYCHIATRIC_EXAM,
    "Neurology": NEUROLOGY_EXAM,
    "Pain Management": PAIN_MANAGEMENT_EXAM,
    "Internal Medicine": ORTHOPEDIC_EXAM,  # default to ortho for general
}

_BODY_PART_TO_REGION: dict[str, str] = {
    "cervical spine": "spine_cervical",
    "thoracic spine": "spine_lumbar",  # use lumbar pool for thoracic
    "lumbar spine": "spine_lumbar",
    "sacrum/coccyx": "spine_lumbar",
    "right shoulder": "shoulder",
    "left shoulder": "shoulder",
    "right knee": "knee",
    "left knee": "knee",
    "right wrist": "wrist_hand",
    "left wrist": "wrist_hand",
    "right hand": "wrist_hand",
    "left hand": "wrist_hand",
    "right hip": "hip",
    "left hip": "hip",
    "right elbow": "elbow",
    "left elbow": "elbow",
    "right ankle": "ankle_foot",
    "left ankle": "ankle_foot",
    "right foot": "ankle_foot",
    "left foot": "ankle_foot",
}

_BODY_PART_TO_ROM_KEY: dict[str, str] = {
    "cervical spine": "cervical spine",
    "lumbar spine": "lumbar spine",
    "right shoulder": "shoulder",
    "left shoulder": "shoulder",
    "right knee": "knee",
    "left knee": "knee",
    "right wrist": "wrist",
    "left wrist": "wrist",
    "right hand": "wrist",
    "left hand": "wrist",
    "right hip": "hip",
    "left hip": "hip",
    "right elbow": "elbow",
    "left elbow": "elbow",
    "right ankle": "ankle",
    "left ankle": "ankle",
    "right foot": "ankle",
    "left foot": "ankle",
}


def get_exam_findings(specialty: str, body_parts: list[str], count: int = 8) -> str:
    """Get specialty-specific exam findings for given body parts.

    Returns a multi-sentence string of clinical exam language drawn from
    the appropriate specialty pool and body-region keys.
    """
    exam_pool = _SPECIALTY_TO_EXAM_MAP.get(specialty, ORTHOPEDIC_EXAM)

    # For psychiatric — pull from several MSE sections
    if exam_pool is PSYCHIATRIC_EXAM:
        sentences: list[str] = []
        for key in ("mental_status_exam", "appearance_behavior", "mood_affect",
                     "thought_process", "cognition"):
            pool = exam_pool.get(key, [])
            if pool:
                sentences.extend(random.sample(pool, min(2, len(pool))))
        random.shuffle(sentences)
        return " ".join(sentences[:count])

    # For pain management — pull from pain & functional assessment
    if exam_pool is PAIN_MANAGEMENT_EXAM:
        sentences = []
        for key in ("pain_assessment", "functional_assessment", "medication_review"):
            pool = exam_pool.get(key, [])
            if pool:
                sentences.extend(random.sample(pool, min(3, len(pool))))
        random.shuffle(sentences)
        return " ".join(sentences[:count])

    # For neurology — pull from several sections
    if exam_pool is NEUROLOGY_EXAM:
        sentences = []
        for key in ("cranial_nerves", "motor_exam", "sensory_exam", "reflex_exam", "coordination"):
            pool = exam_pool.get(key, [])
            if pool:
                sentences.extend(random.sample(pool, min(2, len(pool))))
        random.shuffle(sentences)
        return " ".join(sentences[:count])

    # Orthopedic — pick sentences from relevant body-region keys
    sentences = []
    for bp in body_parts:
        region = _BODY_PART_TO_REGION.get(bp.lower())
        if region and region in exam_pool:
            pool = exam_pool[region]
            sentences.extend(random.sample(pool, min(4, len(pool))))

    # Fill from spine_lumbar if we didn't get enough
    if len(sentences) < count:
        fallback = exam_pool.get("spine_lumbar", exam_pool.get("shoulder", []))
        sentences.extend(random.sample(fallback, min(count - len(sentences), len(fallback))))

    random.shuffle(sentences)
    return " ".join(sentences[:count])


def get_rom_table(body_parts: list[str]) -> list[dict[str, Any]]:
    """Generate ROM measurement data (measured vs. normal) with realistic deficits.

    Returns a list of dicts with keys: body_part, movement, normal, measured, deficit.
    """
    rows: list[dict[str, Any]] = []
    for bp in body_parts:
        rom_key = _BODY_PART_TO_ROM_KEY.get(bp.lower())
        if not rom_key or rom_key not in ROM_NORMAL_VALUES:
            continue
        movements = ROM_NORMAL_VALUES[rom_key]
        for _move_key, (label, normal) in movements.items():
            # Generate a realistic deficit (50-90% of normal)
            deficit_pct = random.uniform(0.50, 0.90)
            measured = int(normal * deficit_pct)
            # Extension at 0 is special (e.g., knee extension)
            if normal == 0:
                measured = random.choice([0, 0, 5, -5])
                deficit = abs(measured)
            else:
                deficit = normal - measured
            rows.append({
                "body_part": bp,
                "movement": label,
                "normal": f"{normal}°",
                "measured": f"{measured}°",
                "deficit": f"{deficit}°",
            })
    return rows


def get_clinical_rationale(decision_type: str, body_parts: list[str], count: int = 4) -> str:
    """Get UR clinical rationale sentences for a decision type (approved/denied/modified)."""
    key = decision_type.lower().replace(" ", "_")
    if key not in UR_CLINICAL_RATIONALE:
        key = "approved"
    pool = UR_CLINICAL_RATIONALE[key]
    selected = random.sample(pool, min(count, len(pool)))
    return "\n\n".join([f"• {s}" for s in selected])


def get_mtus_citations(body_parts: list[str], count: int = 3) -> list[str]:
    """Get relevant MTUS guideline citations based on body parts."""
    categories: list[str] = []
    for bp in body_parts:
        bp_lower = bp.lower()
        if "spine" in bp_lower or "lumbar" in bp_lower or "cervical" in bp_lower:
            categories.extend(["spine_conservative", "spine_surgical"])
        elif any(kw in bp_lower for kw in ["shoulder", "elbow", "wrist", "hand"]):
            categories.append("upper_extremity")
        elif "psyche" in bp_lower:
            categories.append("opioid_guidelines")  # often co-prescribed
        else:
            categories.append("physical_therapy")

    categories = list(set(categories))
    if not categories:
        categories = ["spine_conservative"]

    citations: list[str] = []
    for cat in categories:
        pool = MTUS_GUIDELINE_CITATIONS.get(cat, [])
        if pool:
            citations.extend(random.sample(pool, min(2, len(pool))))

    random.shuffle(citations)
    return citations[:count]


def get_chronology_description(event_type: str, **kwargs: Any) -> str:
    """Get a varied chronology event description for the given event type.

    Supports placeholder substitution via kwargs.
    """
    pool = CHRONOLOGY_EVENT_DESCRIPTIONS.get(event_type, [])
    if not pool:
        return f"Medical event documented ({event_type})."
    desc = random.choice(pool)
    # Replace placeholders with provided values or defaults
    defaults = {
        "pain": str(random.randint(5, 8)),
        "progress": random.choice(["mild improvement", "no significant change", "worsening symptoms", "gradual improvement"]),
        "exam_finding": random.choice(["persistent restricted ROM", "tenderness to palpation", "improved strength", "unchanged neurological exam"]),
        "weeks": str(random.choice([2, 3, 4, 6])),
        "pain_quality": random.choice(["constant and aching", "intermittent and sharp", "burning and radiating"]),
        "limitation": random.choice(["lifting", "prolonged sitting", "overhead reaching", "walking"]),
        "symptom_status": random.choice(["stable", "slowly improving", "unchanged", "fluctuating"]),
        "session_num": str(random.randint(1, 24)),
        "rom_change": random.choice(["5-degree improvement in flexion", "stable ROM measurements", "mild improvement in extension"]),
        "body_part": kwargs.get("body_part", "the affected area"),
        "mri_finding": random.choice(["disc herniation", "rotator cuff tear", "meniscal tear", "degenerative changes"]),
        "xray_finding": random.choice(["mild degenerative changes", "loss of disc height", "no acute abnormality"]),
        "us_finding": random.choice(["partial-thickness tear", "tendinopathy", "joint effusion"]),
        "condition": random.choice(["disc herniation", "spinal stenosis", "radiculopathy"]),
        "surgical_rec": random.choice(["is not recommended", "is recommended", "may be considered if conservative measures fail"]),
        "specialty": random.choice(["orthopedic", "pain management", "neurosurgical"]),
        "duration": random.choice(["4-6 weeks", "6-8 weeks", "3 months"]),
        "level": random.choice(["L4-L5", "L5-S1", "C5-C6", "C6-C7"]),
        "muscle_group": random.choice(["bilateral trapezius", "cervical paraspinals", "lumbar paraspinals"]),
        "levels": random.choice(["L3-L4 and L4-L5", "C3-C4 and C4-C5"]),
        "joint": random.choice(["right shoulder", "right knee", "left hip"]),
        "procedure": random.choice(["lumbar microdiscectomy", "arthroscopic rotator cuff repair", "carpal tunnel release"]),
        "ur_decision": random.choice(["was denied", "was approved with modification", "was deferred pending additional documentation"]),
        "imr_outcome": random.choice(["upheld (denial maintained)", "overturned (treatment authorized)"]),
        "imr_followup": random.choice(["Treatment may now proceed.", "Treating physician to explore alternative treatments."]),
        "treatment": random.choice(["MRI", "epidural steroid injection", "physical therapy extension", "surgical consultation"]),
        "old_med": random.choice(["Ibuprofen 800mg", "Gabapentin 300mg", "Tramadol 50mg"]),
        "reason": random.choice(["GI side effects", "inadequate pain control", "drowsiness"]),
        "new_med": random.choice(["Meloxicam 15mg", "Pregabalin 75mg", "Duloxetine 60mg"]),
        "mme": str(random.choice([30, 45, 60, 75])),
    }
    defaults.update(kwargs)
    for key, val in defaults.items():
        desc = desc.replace(f"{{{key}}}", str(val))
    return desc


def get_record_review_items(body_parts: list[str], position: str = "employee",
                            count: int = 15) -> list[str]:
    """Get a list of reviewed medical record line items with case-specific details."""
    items = list(RECORD_REVIEW_ITEMS)
    # Substitute placeholders
    bp_str = ", ".join(body_parts[:2]) if body_parts else "affected area"
    result = []
    for item in items:
        filled = item.replace("{body_part}", bp_str).replace("{position}", position)
        result.append(filled)
    random.shuffle(result)
    return result[:count]


def get_future_medical_items(body_parts: list[str], count: int = 8) -> list[str]:
    """Get future medical treatment recommendations keyed to body part categories."""
    items: list[str] = []
    for bp in body_parts:
        bp_lower = bp.lower()
        if "spine" in bp_lower or "lumbar" in bp_lower or "cervical" in bp_lower:
            items.extend(FUTURE_MEDICAL_ITEMS.get("spine", []))
        elif any(kw in bp_lower for kw in ["shoulder", "elbow", "wrist", "hand"]):
            items.extend(FUTURE_MEDICAL_ITEMS.get("upper_extremity", []))
        elif any(kw in bp_lower for kw in ["hip", "knee", "ankle", "foot"]):
            items.extend(FUTURE_MEDICAL_ITEMS.get("lower_extremity", []))
        elif "psyche" in bp_lower:
            items.extend(FUTURE_MEDICAL_ITEMS.get("psyche", []))

    if not items:
        items = FUTURE_MEDICAL_ITEMS.get("spine", [])

    items = list(set(items))
    random.shuffle(items)
    return items[:count]


def get_treatment_narrative(treatment_type: str, count: int = 3) -> str:
    """Get treatment narrative sentences for a given treatment type."""
    pool = TREATMENT_NARRATIVES.get(treatment_type, TREATMENT_NARRATIVES["conservative"])
    selected = random.sample(pool, min(count, len(pool)))
    return " ".join(selected)


def get_functional_capacity(count: int = 5) -> str:
    """Get functional capacity description sentences."""
    selected = random.sample(FUNCTIONAL_CAPACITY_DESCRIPTIONS, min(count, len(FUNCTIONAL_CAPACITY_DESCRIPTIONS)))
    return " ".join(selected)


# ---------------------------------------------------------------------------
# Prior Treatment Chief Complaints (pre-injury visit language)
# ---------------------------------------------------------------------------

PRIOR_TREATMENT_CHIEF_COMPLAINTS: list[str] = [
    "Patient presents for routine follow-up of chronic {body_part} condition.",
    "New patient evaluation for gradual onset {body_part} discomfort.",
    "Return visit for ongoing management of {body_part} symptoms.",
    "Patient reports intermittent {body_part} pain, worse with activity.",
    "Follow-up evaluation for previously diagnosed {body_part} strain.",
    "Annual physical examination; patient notes occasional {body_part} stiffness.",
    "Patient seeks evaluation for recurrent {body_part} pain not responding to OTC medications.",
    "Referred by primary care for specialty evaluation of persistent {body_part} complaints.",
]


# ---------------------------------------------------------------------------
# Medications by Specialty (for subpoenaed record medication lists)
# ---------------------------------------------------------------------------

MEDICATIONS_BY_SPECIALTY: dict[str, list[tuple[str, str, str]]] = {
    # (medication_name, dosage, frequency)
    "Internal Medicine": [
        ("Lisinopril", "10 mg", "once daily"),
        ("Metformin", "500 mg", "twice daily"),
        ("Atorvastatin", "20 mg", "once daily at bedtime"),
        ("Omeprazole", "20 mg", "once daily before breakfast"),
        ("Amlodipine", "5 mg", "once daily"),
        ("Metoprolol Tartrate", "25 mg", "twice daily"),
    ],
    "Orthopedic Surgery": [
        ("Naproxen", "500 mg", "twice daily with food"),
        ("Cyclobenzaprine", "10 mg", "three times daily"),
        ("Meloxicam", "15 mg", "once daily"),
        ("Tramadol", "50 mg", "every 6 hours as needed"),
        ("Gabapentin", "300 mg", "three times daily"),
        ("Calcium + Vitamin D", "600 mg/400 IU", "twice daily"),
    ],
    "Chiropractic": [
        ("Ibuprofen", "600 mg", "three times daily with food"),
        ("Methocarbamol", "750 mg", "four times daily"),
        ("Topical Diclofenac Gel", "1%", "four times daily to affected area"),
        ("Magnesium Citrate", "400 mg", "once daily"),
    ],
    "Physical Therapy": [
        ("Ibuprofen", "400 mg", "three times daily as needed"),
        ("Acetaminophen", "500 mg", "every 6 hours as needed"),
        ("Topical Menthol Cream", "4%", "as needed to affected area"),
    ],
    "Pain Management": [
        ("Gabapentin", "300 mg", "three times daily"),
        ("Duloxetine", "60 mg", "once daily"),
        ("Pregabalin", "75 mg", "twice daily"),
        ("Tramadol", "50 mg", "every 6 hours as needed"),
        ("Lidocaine Patch", "5%", "12 hours on / 12 hours off"),
        ("Tizanidine", "4 mg", "three times daily"),
        ("Meloxicam", "15 mg", "once daily"),
    ],
    "Physical Medicine & Rehabilitation (PM&R)": [
        ("Naproxen", "500 mg", "twice daily"),
        ("Baclofen", "10 mg", "three times daily"),
        ("Gabapentin", "300 mg", "three times daily"),
        ("Cyclobenzaprine", "5 mg", "at bedtime"),
        ("Vitamin D3", "2000 IU", "once daily"),
    ],
    "Neurology": [
        ("Gabapentin", "300 mg", "three times daily"),
        ("Topiramate", "25 mg", "twice daily"),
        ("Amitriptyline", "25 mg", "at bedtime"),
        ("Pregabalin", "75 mg", "twice daily"),
        ("Carbamazepine", "200 mg", "twice daily"),
        ("Methylprednisolone Dose Pack", "4 mg", "per taper schedule"),
    ],
}


def get_prior_chief_complaint(body_parts: list[str]) -> str:
    """Get a prior treatment chief complaint with body part substitution."""
    body_part = body_parts[0] if body_parts else "musculoskeletal"
    template = random.choice(PRIOR_TREATMENT_CHIEF_COMPLAINTS)
    return template.format(body_part=body_part)
