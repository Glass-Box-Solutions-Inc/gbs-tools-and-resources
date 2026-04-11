"""
QME/AME Report Template — Specialty-dispatched comprehensive medical-legal report.

Generates 5-15 page reports with specialty-specific examination findings,
AMA Guides 5th Edition impairment ratings, and detailed clinical narratives.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import random
from datetime import date as _date

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from data.content_pools import (
    get_exam_findings,
    get_functional_capacity,
    get_future_medical_items,
    get_treatment_narrative,
)
from data.wc_constants import (
    ICD10_CODES,
    MEDICATIONS,
    MEDICATIONS_BY_SPECIALTY,
    PHYSICAL_EXAM_VITALS,
    WORK_RESTRICTIONS,
)
from pdf_templates.base_template import BaseTemplate


class QmeAmeReport(BaseTemplate):
    """Qualified Medical Evaluator / Agreed Medical Evaluator comprehensive report."""

    def build_story(self, doc_spec):
        """Build 5-15 page QME/AME report with specialty dispatch."""
        story = []
        qme = self.case.qme_physician or self.case.treating_physician
        injury = self.case.injuries[0] if self.case.injuries else None
        specialty = qme.specialty
        body_parts = injury.body_parts if injury else []
        variant = doc_spec.context.get("variant", "") if doc_spec.context else ""

        # --- Letterhead ---
        story.extend(self.make_letterhead(qme.full_name, qme.address, qme.phone))
        story.append(Spacer(1, 0.3 * inch))

        # --- Patient & claim info ---
        story.extend(self.make_patient_header())
        story.append(Spacer(1, 0.2 * inch))
        story.extend(self.make_claim_reference_block())
        story.append(Spacer(1, 0.3 * inch))

        # --- Title ---
        title = "QUALIFIED MEDICAL EVALUATOR REPORT"
        if "ame" in variant:
            title = "AGREED MEDICAL EVALUATOR REPORT"
        if "supplemental" in variant:
            title = f"SUPPLEMENTAL {title}"
        story.append(Paragraph(f"<b>{title}</b>", self.styles["CenterBold"]))
        story.append(Spacer(1, 0.2 * inch))

        # Exam date & specialty
        story.append(Paragraph(
            f"<b>Date of Examination:</b> {doc_spec.doc_date.strftime('%B %d, %Y')}",
            self.styles["BodyText14"],
        ))
        story.append(Paragraph(
            f"<b>Specialty:</b> {specialty}", self.styles["BodyText14"],
        ))
        story.append(Paragraph(
            f"<b>Evaluation Type:</b> {'AME' if 'ame' in variant else 'QME'} — "
            f"{'Supplemental' if 'supplemental' in variant else 'Initial'} Evaluation",
            self.styles["BodyText14"],
        ))
        story.append(Spacer(1, 0.3 * inch))

        # --- 1. History of Present Injury (2-3 paragraphs) ---
        story.extend(self._build_history(injury, doc_spec))

        # --- 2. Review of Medical Records ---
        story.extend(self._build_records_review(doc_spec))

        # --- 3. Chief Complaints ---
        story.extend(self._build_chief_complaints(injury))

        # --- 4. Physical Examination (specialty-dispatched) ---
        story.extend(self._build_physical_exam(specialty, body_parts, doc_spec))

        # --- 5. Diagnostic Review ---
        story.extend(self._build_diagnostic_review(injury))

        # --- 6. Impairment Rating (AMA Guides 5th Ed) ---
        story.extend(self.impairment_rating_section())

        # Phase 6: Record WPI to accumulator so downstream memos can cite it
        acc = self._get_accumulator(doc_spec)
        if acc is not None:
            from data.ama_guides_content import generate_impairment_narrative
            _narrative, total_wpi, _ratings = generate_impairment_narrative(
                body_parts, specialty, apportionment_pct=0
            )
            pd_pct = round(total_wpi * 1.4, 1)  # simplified WPI→PD conversion
            acc.record_document(
                title=doc_spec.title,
                doc_date=doc_spec.doc_date,
                subtype=doc_spec.subtype.value,
                wpi_rating=total_wpi,
                pd_percentage=pd_pct,
            )

        # --- 7. Future Medical Treatment ---
        story.extend(self._build_future_medical(body_parts))

        # --- 8. Work Restrictions ---
        story.extend(self._build_work_restrictions())

        # --- 9. Conclusions ---
        story.extend(self._build_conclusions(injury, doc_spec))

        # --- Signature ---
        story.append(Spacer(1, 0.4 * inch))
        story.extend(self.make_signature_block(
            qme.full_name, specialty, qme.license_number,
        ))
        story.append(Spacer(1, 0.1 * inch))
        qme_number = f"QME{random.randint(10000, 99999)}"
        story.append(Paragraph(
            f"<i>Qualified Medical Evaluator #{qme_number}</i>",
            self.styles["SmallItalic"],
        ))
        story.append(Paragraph(
            "<i>I declare under penalty of perjury that this report is true and correct "
            "to the best of my knowledge.</i>",
            self.styles["SmallItalic"],
        ))

        return story

    # ----- Section builders -----

    def _build_history(self, injury, doc_spec):
        """History of Present Injury — 4-5 paragraphs for substantial content."""
        elements = []
        applicant_age = (_date.today() - self.case.applicant.date_of_birth).days // 365
        bp_str = ", ".join(injury.body_parts).lower() if injury else "body"
        mechanism = injury.mechanism.lower() if injury else "workplace incident"
        doi = self.case.timeline.date_of_injury.strftime("%m/%d/%Y")
        position = self.case.employer.position.lower()
        employer = self.case.employer.company_name

        para1 = (
            f"The patient is a {applicant_age}-year-old {position} "
            f"who sustained a work-related injury on {doi} while employed by "
            f"{employer}. The mechanism of injury involved "
            f"{mechanism}. The patient reports immediate onset of symptoms affecting "
            f"the {bp_str}. At the time of injury, the patient had been employed by "
            f"{employer} for approximately "
            f"{(_date.today() - self.case.employer.hire_date).days // 365} years. "
            f"The patient's job duties included physical tasks requiring "
            f"{random.choice(['lifting up to 50 pounds, prolonged standing, and repetitive bending', 'sustained physical labor including pushing, pulling, and carrying', 'regular overhead work, climbing, and operating heavy equipment'])}."
        )

        para2 = (
            f"Following the injury, the patient reported the incident to "
            f"{random.choice(['the supervisor', 'management', 'the shift lead'])} and sought "
            f"medical attention {random.choice(['the same day at an emergency department', 'within 24 hours at an urgent care facility', 'the following day at the treating physician office'])}. "
            f"Initial evaluation revealed {random.choice(['tenderness, restricted range of motion, and muscle guarding', 'acute pain, swelling, and functional limitation', 'significant pain with limited mobility and neurological symptoms'])} "
            f"in the {bp_str}. Diagnostic imaging was obtained including "
            f"{random.choice(['X-rays which revealed no acute fracture but noted degenerative changes', 'MRI which demonstrated structural pathology correlating with symptoms', 'X-rays and subsequent MRI for further evaluation of the injury'])}."
        )

        treatment_type = random.choice(["conservative", "interventional", "physical_therapy"])
        treatment_narrative = get_treatment_narrative(treatment_type, count=3)
        para3 = (
            f"Since the date of injury, the patient has received treatment from "
            f"{self.case.treating_physician.full_name}, {self.case.treating_physician.specialty}, "
            f"at {self.case.treating_physician.facility}. "
            f"{treatment_narrative}"
        )

        para4 = (
            f"The patient describes current symptoms as {random.choice(['persistent and limiting daily activities', 'variable with good and bad days but generally worsening', 'constant with intermittent sharp exacerbations'])}. "
            f"The patient reports pain levels ranging from {random.randint(3, 5)}/10 at best to "
            f"{random.randint(7, 9)}/10 at worst, with an average pain level of {random.randint(5, 7)}/10. "
            f"Aggravating factors include {random.choice(['prolonged sitting, standing, and physical exertion', 'lifting, bending, twisting, and cold weather', 'repetitive motion, sustained positions, and stress'])}. "
            f"Alleviating factors include {random.choice(['rest, medication, and ice/heat application', 'lying down, prescribed medications, and activity modification', 'position changes, medications, and avoidance of aggravating activities'])}."
        )

        para5 = (
            f"The patient reports that the injury has significantly impacted their ability to "
            f"perform work duties and activities of daily living. Prior to this injury, the patient "
            f"was able to perform all job duties without limitation and was physically active. "
            f"The patient denies any prior injuries to the {bp_str}, denies any prior workers' "
            f"compensation claims, and denies any pre-existing conditions affecting the "
            f"claimed body parts. The patient's pre-injury health was described as "
            f"{random.choice(['excellent with no limitations', 'good with no significant medical history', 'generally healthy with no prior orthopedic or neurological issues'])}."
        )

        elements.extend(self.make_section("HISTORY OF PRESENT INJURY", para1))
        elements.append(Paragraph(para2, self.styles["BodyText14"]))
        elements.append(Spacer(1, 0.08 * inch))
        elements.append(Paragraph(para3, self.styles["BodyText14"]))
        elements.append(Spacer(1, 0.08 * inch))
        elements.append(Paragraph(para4, self.styles["BodyText14"]))
        elements.append(Spacer(1, 0.08 * inch))
        elements.append(Paragraph(para5, self.styles["BodyText14"]))
        elements.append(Spacer(1, 0.15 * inch))
        return elements

    def _build_records_review(self, doc_spec):
        """Review of Medical Records — 10-20 items."""
        elements = []
        records_list = self.medical_record_review_list(doc_spec.doc_date)
        elements.extend(self.make_section("REVIEW OF MEDICAL RECORDS", (
            "The following medical records were reviewed in preparation for this evaluation:\n\n"
            + records_list
        )))
        elements.append(Spacer(1, 0.15 * inch))
        return elements

    def _build_chief_complaints(self, injury):
        """Chief Complaints — per body part."""
        elements = []
        if not injury:
            elements.extend(self.make_section("CHIEF COMPLAINTS", self.lorem_medical(4)))
            return elements

        complaints = []
        pain_descriptors = ["constant dull aching", "intermittent sharp and stabbing",
                           "burning and radiating", "throbbing and pressure-like",
                           "deep aching with occasional sharp exacerbations"]
        for bp in injury.body_parts:
            pain_level = random.randint(4, 8)
            descriptor = random.choice(pain_descriptors)
            aggravators = random.choice([
                "prolonged sitting, standing, and bending",
                "lifting, reaching, and repetitive motion",
                "physical activity and position changes",
                "cold weather, stress, and overexertion",
            ])
            complaints.append(
                f"<b>{bp.title()}:</b> Patient reports {descriptor} pain, rated {pain_level}/10 on "
                f"average. Pain is aggravated by {aggravators}. Patient reports associated "
                f"{random.choice(['stiffness and limited motion', 'numbness and tingling', 'weakness and fatigue', 'swelling and tenderness'])}."
            )

        elements.extend(self.make_section("CHIEF COMPLAINTS", "\n\n".join(complaints)))
        elements.append(Spacer(1, 0.15 * inch))
        return elements

    def _build_physical_exam(self, specialty, body_parts, doc_spec):
        """Physical Examination — specialty-dispatched."""
        elements = []
        elements.append(Paragraph(
            "<b>PHYSICAL EXAMINATION FINDINGS</b>", self.styles["SectionHeader"],
        ))
        elements.append(Spacer(1, 0.1 * inch))

        # Vitals
        vitals = PHYSICAL_EXAM_VITALS
        bp_vital = random.choice(vitals["blood_pressure"])
        hr = random.choice(vitals["heart_rate"])
        rr = random.choice(vitals["respiratory_rate"])
        temp = random.choice(vitals["temperature"])
        hw = random.choice(vitals["height_weight"])
        vitals_text = (
            f"<b>Vital Signs:</b> Blood Pressure: {bp_vital[0]} ({bp_vital[1]}), "
            f"Heart Rate: {hr[0]} bpm ({hr[1]}), Respiratory Rate: {rr[0]} ({rr[1]}), "
            f"Temperature: {temp[0]} ({temp[1]}), Height/Weight: {hw[0]} ({hw[1]})"
        )
        elements.append(Paragraph(vitals_text, self.styles["BodyText14"]))
        elements.append(Spacer(1, 0.1 * inch))

        # General appearance
        elements.append(Paragraph(
            "Patient presents as a well-developed, well-nourished individual in no acute distress. "
            "Patient ambulates independently and follows commands appropriately. "
            "The patient is cooperative with the examination and appears to give appropriate effort.",
            self.styles["BodyText14"],
        ))
        elements.append(Spacer(1, 0.1 * inch))

        # Specialty-specific exam
        is_psych = "Psychiatry" in specialty
        is_neuro = "Neurology" in specialty
        is_pain = "Pain" in specialty

        if is_psych:
            elements.extend(self._build_psych_exam())
        elif is_neuro:
            elements.extend(self._build_neuro_exam(body_parts))
        elif is_pain:
            elements.extend(self._build_pain_exam(body_parts))
        else:
            elements.extend(self._build_ortho_exam(body_parts))

        elements.append(Spacer(1, 0.15 * inch))
        return elements

    def _build_ortho_exam(self, body_parts):
        """Orthopedic exam: ROM table + special tests + motor + sensory + gait."""
        elements = []

        # Specialty exam findings (detailed)
        findings = get_exam_findings("Orthopedic Surgery", body_parts, count=12)
        elements.append(Paragraph(findings, self.styles["BodyText14"]))
        elements.append(Spacer(1, 0.15 * inch))

        # ROM table
        rom_table = self.rom_findings_table()
        if not isinstance(rom_table, Spacer):
            elements.append(Paragraph("<b>Range of Motion Measurements:</b>", self.styles["BodyText14"]))
            elements.append(Spacer(1, 0.05 * inch))
            elements.append(rom_table)
            elements.append(Spacer(1, 0.15 * inch))

        # Motor strength summary
        motor_findings = random.choice([
            "Motor strength testing: Upper extremities — deltoid 4/5 R, 5/5 L; biceps 4+/5 R, 5/5 L; triceps 5/5 bilaterally; grip strength 30 kg R, 45 kg L. Lower extremities — hip flexion 5/5 bilaterally; knee extension 5/5 bilaterally; ankle dorsiflexion 4+/5 L, 5/5 R; EHL 4/5 L, 5/5 R.",
            "Motor strength is 5/5 throughout bilateral upper and lower extremities except as noted above. No atrophy is observed. Grip strength is symmetric bilaterally.",
            "Motor strength testing reveals focal weakness in the affected extremity as detailed above. Contralateral strength is 5/5 throughout, serving as internal control.",
        ])
        elements.append(Paragraph(f"<b>Motor Strength Summary:</b> {motor_findings}", self.styles["BodyText14"]))
        elements.append(Spacer(1, 0.1 * inch))

        # Sensory examination
        sensory = random.choice([
            "Sensory examination reveals diminished light touch and pinprick in the affected dermatome. Vibration and proprioception are intact bilaterally. Two-point discrimination is within normal limits.",
            "Sensory examination is intact to light touch, pinprick, and vibration in all tested dermatomes bilaterally. No dermatomal pattern of sensory loss identified.",
            "Light touch is diminished in the affected distribution. Temperature discrimination is intact. Romberg test is negative.",
        ])
        elements.append(Paragraph(f"<b>Sensory Examination:</b> {sensory}", self.styles["BodyText14"]))
        elements.append(Spacer(1, 0.1 * inch))

        # Gait analysis
        gait_desc = random.choice([
            "Gait is antalgic with shortened stride length and reduced arm swing on the affected side. The patient ambulates without assistive device but demonstrates guarded posture. Tandem gait is performed with mild difficulty. Heel and toe walking are performed but reproduce symptoms.",
            "Gait is mildly antalgic; patient ambulates without assistive device. Station is stable. The patient demonstrates difficulty with single-leg stance on the affected side. Trendelenburg test is negative bilaterally.",
            "Gait pattern is grossly normal with slight favoring of the affected lower extremity. The patient can heel-walk and toe-walk bilaterally. Tandem gait is performed without difficulty.",
        ])
        elements.append(Paragraph(f"<b>Gait Analysis:</b> {gait_desc}", self.styles["BodyText14"]))
        return elements

    def _build_psych_exam(self):
        """Psychiatric exam: MSE + psychological testing + DSM-5 + GAF."""
        elements = []
        from data.content_pools import PSYCHIATRIC_EXAM

        # Mental Status Examination
        elements.append(Paragraph("<b>Mental Status Examination:</b>", self.styles["BodyText14"]))
        elements.append(Spacer(1, 0.05 * inch))
        for section_key in ("mental_status_exam", "appearance_behavior", "mood_affect",
                            "thought_process", "cognition"):
            pool = PSYCHIATRIC_EXAM.get(section_key, [])
            if pool:
                findings = random.sample(pool, min(3, len(pool)))
                label = section_key.replace("_", " ").title()
                elements.append(Paragraph(
                    f"<b>{label}:</b> {' '.join(findings)}", self.styles["BodyText14"],
                ))
                elements.append(Spacer(1, 0.05 * inch))

        # Psychological Testing
        testing_pool = PSYCHIATRIC_EXAM.get("psychological_testing", [])
        if testing_pool:
            results = random.sample(testing_pool, min(4, len(testing_pool)))
            elements.append(Paragraph("<b>Psychological Testing Results:</b>", self.styles["BodyText14"]))
            for r in results:
                elements.append(Paragraph(f"• {r}", self.styles["BodyText14"]))
            elements.append(Spacer(1, 0.1 * inch))

        # DSM-5 Criteria
        dsm_pool = PSYCHIATRIC_EXAM.get("dsm5_criteria", [])
        if dsm_pool:
            dsm = random.choice(dsm_pool)
            elements.append(Paragraph(f"<b>DSM-5 Diagnostic Impression:</b> {dsm}", self.styles["BodyText14"]))
            elements.append(Spacer(1, 0.1 * inch))

        # GAF Assessment
        gaf_pool = PSYCHIATRIC_EXAM.get("gaf_assessment", [])
        if gaf_pool:
            gaf_findings = random.sample(gaf_pool, min(3, len(gaf_pool)))
            elements.append(Paragraph(
                "<b>Global Assessment of Functioning:</b> " + " ".join(gaf_findings),
                self.styles["BodyText14"],
            ))
            elements.append(Spacer(1, 0.1 * inch))

        # Functional Assessment
        func_pool = PSYCHIATRIC_EXAM.get("functional_assessment", [])
        if func_pool:
            func_findings = random.sample(func_pool, min(4, len(func_pool)))
            elements.append(Paragraph("<b>Functional Assessment:</b>", self.styles["BodyText14"]))
            for f in func_findings:
                elements.append(Paragraph(f"• {f}", self.styles["BodyText14"]))

        return elements

    def _build_neuro_exam(self, body_parts):
        """Neurology exam: cranial nerves + motor + sensory + reflexes + coordination + EMG/NCV."""
        elements = []
        findings = get_exam_findings("Neurology", body_parts, count=12)
        elements.append(Paragraph(findings, self.styles["BodyText14"]))
        elements.append(Spacer(1, 0.15 * inch))

        # ROM table if applicable
        rom_table = self.rom_findings_table()
        if not isinstance(rom_table, Spacer):
            elements.append(Paragraph("<b>Range of Motion Measurements:</b>", self.styles["BodyText14"]))
            elements.append(Spacer(1, 0.05 * inch))
            elements.append(rom_table)
            elements.append(Spacer(1, 0.1 * inch))

        # EMG/NCV results
        from data.content_pools import NEUROLOGY_EXAM
        emg_pool = NEUROLOGY_EXAM.get("emg_ncv", [])
        if emg_pool:
            emg_findings = random.sample(emg_pool, min(3, len(emg_pool)))
            elements.append(Paragraph(
                "<b>Electrodiagnostic Studies (EMG/NCV):</b> " + " ".join(emg_findings),
                self.styles["BodyText14"],
            ))

        return elements

    def _build_pain_exam(self, body_parts):
        """Pain management exam: pain assessment + functional + medication review."""
        elements = []
        findings = get_exam_findings("Pain Management", body_parts, count=10)
        elements.append(Paragraph(findings, self.styles["BodyText14"]))
        elements.append(Spacer(1, 0.15 * inch))

        # ROM table
        rom_table = self.rom_findings_table()
        if not isinstance(rom_table, Spacer):
            elements.append(Paragraph("<b>Range of Motion Measurements:</b>", self.styles["BodyText14"]))
            elements.append(Spacer(1, 0.05 * inch))
            elements.append(rom_table)
            elements.append(Spacer(1, 0.1 * inch))

        # Intervention history
        from data.content_pools import PAIN_MANAGEMENT_EXAM
        intervention_pool = PAIN_MANAGEMENT_EXAM.get("intervention_history", [])
        if intervention_pool:
            interventions = random.sample(intervention_pool, min(3, len(intervention_pool)))
            elements.append(Paragraph("<b>Intervention History:</b>", self.styles["BodyText14"]))
            for item in interventions:
                elements.append(Paragraph(f"• {item}", self.styles["BodyText14"]))

        return elements

    def _build_diagnostic_review(self, injury):
        """Diagnostic Review — body-part-specific imaging/lab findings."""
        elements = []
        if not injury:
            elements.extend(self.make_section("DIAGNOSTIC REVIEW", self.lorem_medical(5)))
            return elements

        findings = []
        for bp in injury.body_parts:
            imaging_type = random.choice(["MRI", "X-ray", "CT scan"])
            finding = random.choice([
                f"disc herniation at the {random.choice(['C5-C6', 'C6-C7', 'L4-L5', 'L5-S1'])} level",
                "degenerative disc disease with moderate foraminal stenosis",
                "partial-thickness rotator cuff tear with subacromial bursitis",
                "meniscal tear, posterior horn, with associated joint effusion",
                "moderate degenerative changes with osteophyte formation",
                "disc bulge without significant neural compression",
                "Grade II ligamentous injury with associated soft tissue edema",
                "chronic tendinopathy with partial tearing",
            ])
            findings.append(
                f"<b>{bp.title()}:</b> {imaging_type} demonstrates {finding}. "
                f"Findings are {random.choice(['consistent with', 'supportive of', 'correlative with'])} "
                f"the clinical presentation."
            )

        elements.extend(self.make_section("DIAGNOSTIC REVIEW", "\n\n".join(findings)))
        elements.append(Spacer(1, 0.15 * inch))
        return elements

    def _build_future_medical(self, body_parts):
        """Future Medical Treatment — 8-12 itemized recommendations."""
        elements = []
        items = get_future_medical_items(body_parts, count=random.randint(8, 12))
        items_text = "\n".join([f"{i+1}. {item}" for i, item in enumerate(items)])
        elements.extend(self.make_section("FUTURE MEDICAL TREATMENT RECOMMENDATIONS", (
            "Based on the evaluation findings, the following future medical treatment "
            "is reasonably required to cure or relieve the effects of the industrial injury:\n\n"
            + items_text
        )))
        elements.append(Spacer(1, 0.15 * inch))
        return elements

    def _build_work_restrictions(self):
        """Work Restrictions — functional capacity language."""
        elements = []
        fc_desc = get_functional_capacity(count=4)
        restrictions = random.sample(WORK_RESTRICTIONS, k=random.randint(3, 6))
        has_restrictions = random.random() > 0.2

        if has_restrictions:
            content = (
                "Based on current functional capacity assessment, the following permanent "
                "work restrictions are recommended:\n\n"
                + "\n".join([f"• {r}" for r in restrictions])
                + f"\n\n{fc_desc}"
            )
        else:
            content = (
                "Patient has reached maximum medical improvement with minimal residual "
                "limitations. No permanent work restrictions are necessary at this time. "
                "The patient may return to full duty without limitations."
            )
        elements.extend(self.make_section("WORK RESTRICTIONS AND FUNCTIONAL CAPACITY", content))
        elements.append(Spacer(1, 0.15 * inch))
        return elements

    def _build_conclusions(self, injury, doc_spec):
        """Conclusions and Medical-Legal Opinions — numbered list with detailed rationale."""
        elements = []
        doi = self.case.timeline.date_of_injury.strftime("%m/%d/%Y")
        bp_str = ", ".join(injury.body_parts).lower() if injury else "the injured area"

        conclusions = [
            f"1. <b>Industrial Causation:</b> The injury sustained on {doi} is industrial in nature and arose out of and in the course of employment with {self.case.employer.company_name}. The mechanism of injury is consistent with the documented medical findings. It is my opinion, to a reasonable degree of medical probability, that the industrial injury is the primary cause of the patient's current condition.",
            f"2. <b>Maximum Medical Improvement:</b> The patient has reached maximum medical improvement (permanent and stationary) as of the date of this evaluation. Further curative treatment is not expected to result in significant improvement in the patient's condition, although palliative and maintenance care remains necessary.",
            f"3. <b>Permanent Impairment:</b> Permanent impairment has been rated per the AMA Guides to the Evaluation of Permanent Impairment, Fifth Edition, as required by LC §4660.1. The impairment rating is based on the patient's condition at the time of maximum medical improvement and reflects the functional limitations documented during this evaluation.",
            f"4. <b>Future Medical Care:</b> Future medical care is reasonably required to cure or relieve the effects of the industrial injury per LC §4600. The recommended future medical treatment is outlined in detail above and includes ongoing medication management, periodic follow-up evaluations, and potential interventional procedures as clinically indicated.",
            f"5. <b>Work Restrictions:</b> {'Permanent work restrictions are recommended as outlined above. The patient is unable to return to the pre-injury occupation and should be evaluated for vocational rehabilitation.' if random.random() > 0.2 else 'No permanent work restrictions are necessary. The patient may return to full duty without limitations.'}",
            f"6. <b>Causation Analysis:</b> The current condition of the {bp_str} is {'entirely' if random.random() > 0.4 else 'predominantly'} attributable to the industrial injury. This opinion is based on the temporal relationship between the injury and symptom onset, the mechanism of injury, the clinical findings, and the absence of pre-existing conditions affecting these body parts.",
            f"7. <b>Apportionment:</b> {'No apportionment is applicable in this case. The entire permanent disability is attributable to the industrial injury. There is no credible evidence of pre-existing pathology contributing to the current impairment.' if random.random() > 0.5 else 'Apportionment has been addressed as outlined in the impairment rating section of this report per LC §4663 and §4664.'}",
        ]

        elements.extend(self.make_section(
            "CONCLUSIONS AND MEDICAL-LEGAL OPINIONS",
            "\n\n".join(conclusions),
        ))

        # Declaration
        elements.append(Spacer(1, 0.1 * inch))
        elements.append(Paragraph(
            "These opinions are rendered to a reasonable degree of medical probability based on "
            "the history obtained, physical examination findings, review of medical records, "
            "and application of established medical guidelines. I reserve the right to supplement "
            "or modify these opinions should additional records or information become available.",
            self.styles["BodyText14"],
        ))
        return elements
