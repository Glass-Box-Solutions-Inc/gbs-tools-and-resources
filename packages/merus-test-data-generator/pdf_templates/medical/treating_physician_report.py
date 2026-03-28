"""
Treating Physician Report Template (PR-2/PR-4) — Specialty-dispatched.

Generates 2-4 page progress reports with variant awareness (PR-2, PR-4, specialty types).
PR-4 variant includes P&S declaration, WPI calculation, and future medical care.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import random

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from data.content_pools import (
    get_exam_findings,
    get_future_medical_items,
    get_treatment_narrative,
)
from data.wc_constants import (
    CPT_CODES,
    ICD10_CODES,
    MEDICATIONS,
    MEDICATIONS_BY_SPECIALTY,
    WORK_RESTRICTIONS,
)
from pdf_templates.base_template import BaseTemplate


class TreatingPhysicianReport(BaseTemplate):
    """PR-2/PR-4 Workers' Compensation treating physician progress report."""

    def build_story(self, doc_spec):
        """Build 2-4 page treating physician report with variant dispatch."""
        story = []
        tp = self.case.treating_physician
        patient = self.case.applicant
        injury = self.case.injuries[0] if self.case.injuries else None
        variant = doc_spec.context.get("variant", "pr2") if doc_spec.context else "pr2"
        specialty = tp.specialty
        body_parts = injury.body_parts if injury else []
        is_pr4 = "pr4" in variant or "final" in variant or "ps" in variant

        # --- Letterhead ---
        story.extend(self.make_letterhead(tp.full_name, tp.address, tp.phone))
        story.append(Spacer(1, 0.3 * inch))

        # --- Patient & claim ---
        story.extend(self.make_patient_header())
        story.append(Spacer(1, 0.2 * inch))
        story.extend(self.make_claim_reference_block())
        story.append(Spacer(1, 0.3 * inch))

        # --- Report header ---
        title = doc_spec.title
        if is_pr4:
            title = "PRIMARY TREATING PHYSICIAN'S REPORT — PERMANENT AND STATIONARY"
        story.append(Paragraph(f"<b>{title}</b>", self.styles["CenterBold"]))
        story.append(Spacer(1, 0.2 * inch))

        story.append(Paragraph(
            f"<b>Date of Service:</b> {doc_spec.doc_date.strftime('%B %d, %Y')}",
            self.styles["BodyText14"],
        ))
        story.append(Paragraph(
            f"<b>Treating Physician:</b> {tp.full_name}, {specialty}",
            self.styles["BodyText14"],
        ))
        if is_pr4:
            story.append(Paragraph(
                "<b>Report Type:</b> PR-4 — Permanent and Stationary Report",
                self.styles["BodyText14"],
            ))
        story.append(Spacer(1, 0.2 * inch))

        # --- Chief Complaints (full paragraph) ---
        story.extend(self._build_chief_complaints(injury))

        # --- Physical Examination (specialty-dispatched) ---
        story.extend(self._build_physical_exam(specialty, body_parts))

        # --- Assessment with ICD-10 ---
        story.extend(self._build_assessment(injury))

        # --- Treatment Plan ---
        story.extend(self._build_treatment_plan(specialty, variant))

        # --- Work Restrictions ---
        story.extend(self._build_work_restrictions(is_pr4))

        # --- Current Medications ---
        story.extend(self._build_medications(specialty))

        # --- PR-4 specific sections ---
        if is_pr4:
            story.extend(self._build_pr4_sections(body_parts))

        # --- Signature ---
        story.extend(self.make_signature_block(tp.full_name, specialty, tp.license_number))

        return story

    def _build_chief_complaints(self, injury):
        """Full paragraph chief complaints with per-body-part symptoms."""
        elements = []
        if not injury:
            elements.extend(self.make_section("CHIEF COMPLAINTS", self.lorem_medical(4)))
            return elements

        complaints_parts = []
        for bp in injury.body_parts:
            pain_level = random.randint(4, 8)
            symptom = random.choice([
                "pain, stiffness, and limited range of motion",
                "persistent aching and functional limitations",
                "intermittent sharp pain with associated weakness",
                "swelling, tenderness, and restricted mobility",
                "radiating pain with numbness and tingling",
            ])
            complaints_parts.append(f"{bp} ({pain_level}/10 — {symptom})")

        content = (
            f"Patient presents today for follow-up evaluation of work-related injuries sustained on "
            f"{self.case.timeline.date_of_injury.strftime('%m/%d/%Y')}. "
            f"Current complaints include: {'; '.join(complaints_parts)}. "
            f"Patient reports that symptoms are {random.choice(['unchanged since last visit', 'slowly improving', 'fluctuating with activity', 'worsening despite treatment'])}. "
            f"The patient rates overall functional status as {random.choice(['significantly limited', 'moderately impaired', 'somewhat improved but still restricted'])}."
        )
        elements.extend(self.make_section("CHIEF COMPLAINTS", content))
        return elements

    def _build_physical_exam(self, specialty, body_parts):
        """Specialty-dispatched physical exam."""
        elements = []
        is_psych = "Psychiatry" in specialty
        is_chiro = "Chiropractic" in specialty
        is_pt = "Physical Therapy" in specialty

        if is_psych:
            # Psychiatric — MSE-based
            from data.content_pools import PSYCHIATRIC_EXAM
            findings = []
            for key in ("mental_status_exam", "mood_affect", "cognition"):
                pool = PSYCHIATRIC_EXAM.get(key, [])
                if pool:
                    findings.extend(random.sample(pool, min(2, len(pool))))
            exam_text = " ".join(findings)
        else:
            exam_text = get_exam_findings(specialty, body_parts, count=random.randint(6, 8))

        elements.extend(self.make_section("PHYSICAL EXAMINATION", exam_text))

        # ROM table for ortho/chiro/PT
        if not is_psych and body_parts:
            rom_table = self.rom_findings_table()
            if not isinstance(rom_table, Spacer):
                elements.append(Spacer(1, 0.05 * inch))
                elements.append(rom_table)
                elements.append(Spacer(1, 0.1 * inch))

        return elements

    def _build_assessment(self, injury):
        """Assessment with ICD-10 codes and clinical correlation."""
        elements = []
        icd_codes = injury.icd10_codes if injury else []
        icd_text = []
        for code in icd_codes[:4]:
            desc = "Unspecified injury"
            for _bp, code_list in ICD10_CODES.items():
                for c, d in code_list:
                    if c == code:
                        desc = d
                        break
            icd_text.append(f"• {code} — {desc}")

        clinical_correlation = random.choice([
            "Clinical findings correlate with imaging studies and are consistent with the documented mechanism of injury.",
            "Objective examination findings are consistent with the stated diagnoses and the industrial mechanism of injury.",
            "Physical examination and diagnostic studies support the working diagnoses listed above.",
            "The patient's subjective complaints are consistent with objective examination findings and diagnostic studies.",
        ])

        assessment_content = (
            f"Based on clinical examination and review of diagnostic studies, patient continues to "
            f"demonstrate findings consistent with work-related {injury.injury_type.value.replace('_', ' ')} "
            f"injury. {clinical_correlation}\n\n"
            f"<b>ICD-10 Diagnoses:</b>\n" + "\n".join(icd_text)
        )
        elements.extend(self.make_section("ASSESSMENT", assessment_content))
        return elements

    def _build_treatment_plan(self, specialty, variant):
        """Treatment plan with specific modalities and goals."""
        elements = []
        all_cpts = [(code, desc) for cat_list in CPT_CODES.values() for code, desc in cat_list]
        selected_cpts = random.sample(all_cpts, k=min(random.randint(2, 4), len(all_cpts)))
        cpt_items = [f"• {code} — {desc}" for code, desc in selected_cpts]

        treatment_type = random.choice(["conservative", "physical_therapy", "medication_management"])
        narrative = get_treatment_narrative(treatment_type, count=2)

        follow_up_weeks = random.choice([2, 3, 4, 6])
        content = (
            f"{narrative}\n\n"
            f"<b>Treatment Plan:</b>\n" + "\n".join(cpt_items) + "\n\n"
            f"<b>Goals:</b> Reduce pain, improve range of motion, restore functional capacity, "
            f"and facilitate return to work.\n\n"
            f"Patient is scheduled for follow-up in {follow_up_weeks} weeks."
        )
        elements.extend(self.make_section("TREATMENT PLAN", content))
        return elements

    def _build_work_restrictions(self, is_pr4):
        """Work restrictions with functional capacity language."""
        elements = []
        restrictions = random.sample(WORK_RESTRICTIONS, k=random.randint(2, 5))
        if is_pr4:
            content = (
                "The patient has reached maximum medical improvement (permanent and stationary). "
                "The following <b>permanent</b> work restrictions are recommended:\n\n"
                + "\n".join([f"• {r}" for r in restrictions])
                + "\n\nThese restrictions are expected to be permanent based on the nature of the injury "
                "and current functional status."
            )
        else:
            content = (
                "Patient remains under the following work restrictions:\n\n"
                + "\n".join([f"• {r}" for r in restrictions])
                + "\n\nThese restrictions are expected to remain in place pending re-evaluation at next visit."
            )
        elements.extend(self.make_section("WORK RESTRICTIONS", content))
        return elements

    def _build_medications(self, specialty):
        """Current medications table — specialty-aware."""
        elements = []
        # Select from specialty pool if available, otherwise general
        specialty_key = None
        if "Psychiatry" in specialty:
            specialty_key = "psychiatric"
        elif "Pain" in specialty:
            specialty_key = "pain_management"
        elif "Neurology" in specialty:
            specialty_key = "neurology"
        elif any(kw in specialty for kw in ["Orthopedic", "Chiropractic", "Physical"]):
            specialty_key = "orthopedic"

        if specialty_key and specialty_key in MEDICATIONS_BY_SPECIALTY:
            med_pool = MEDICATIONS_BY_SPECIALTY[specialty_key]
        else:
            med_pool = MEDICATIONS

        meds = random.sample(med_pool, k=min(random.randint(3, 5), len(med_pool)))
        med_data = [["Medication", "Dosage", "Frequency"]]
        for med_entry in meds:
            med_data.append(list(med_entry[:3]))

        med_table = Table(med_data, colWidths=[2.5 * inch, 1.2 * inch, 1.5 * inch])
        med_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("TOPPADDING", (0, 1), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ]))

        elements.append(Paragraph("<b>CURRENT MEDICATIONS</b>", self.styles["SectionHeader"]))
        elements.append(Spacer(1, 0.1 * inch))
        elements.append(med_table)
        elements.append(Spacer(1, 0.3 * inch))
        return elements

    def _build_pr4_sections(self, body_parts):
        """PR-4 specific: P&S declaration, WPI, future medical, RTW assessment."""
        elements = []

        # P&S Declaration
        ps_content = (
            "The patient has been evaluated on multiple occasions and has received appropriate "
            "medical treatment including physical therapy, medication management, and diagnostic studies. "
            "Based on the clinical examination findings, review of diagnostic studies, and the "
            "patient's clinical course, it is my medical opinion that the patient has reached "
            "<b>maximum medical improvement (permanent and stationary)</b> as of the date of this report. "
            "Further improvement with treatment is not anticipated."
        )
        elements.extend(self.make_section("PERMANENT AND STATIONARY STATUS", ps_content))
        elements.append(Spacer(1, 0.1 * inch))

        # WPI calculation (using AMA Guides narrative)
        elements.extend(self.impairment_rating_section())

        # Future Medical Care
        items = get_future_medical_items(body_parts, count=random.randint(5, 8))
        fmt_content = (
            "The following future medical treatment is reasonably required to cure or relieve "
            "the effects of the industrial injury per LC §4600:\n\n"
            + "\n".join([f"• {item}" for item in items])
        )
        elements.extend(self.make_section("FUTURE MEDICAL CARE", fmt_content))
        elements.append(Spacer(1, 0.1 * inch))

        # Return to Work Assessment
        rtw_content = random.choice([
            "Based on the permanent work restrictions outlined above, the patient is unable to "
            "return to their pre-injury occupation. The patient may be a candidate for vocational "
            "rehabilitation and should be referred for a supplemental job displacement benefit (SJDB) "
            "voucher evaluation per LC §4658.7.",
            "The patient may return to modified duty within the restrictions outlined above. "
            "The employer should be advised of the permanent restrictions and the need for accommodations.",
            "The patient is unable to return to gainful employment in any capacity based on the "
            "severity of permanent functional limitations. A vocational evaluation is recommended.",
        ])
        elements.extend(self.make_section("RETURN TO WORK ASSESSMENT", rtw_content))

        return elements
