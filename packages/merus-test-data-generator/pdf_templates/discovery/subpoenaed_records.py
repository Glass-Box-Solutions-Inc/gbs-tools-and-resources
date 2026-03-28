"""
Subpoenaed Records template for Workers' Compensation discovery.
Produces a cover sheet + multi-page clinical records from prior providers.

Supports both medical and employment subpoenaed record subtypes.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from pdf_templates.base_template import BaseTemplate


class SubpoenaedRecords(BaseTemplate):
    """Generates subpoenaed records: cover sheet + actual clinical content pages."""

    def build_story(self, doc_spec: Any) -> list:
        """Build the full subpoenaed records story."""
        subtype = doc_spec.subtype.value if hasattr(doc_spec.subtype, "value") else str(doc_spec.subtype)

        # Select provider and facility
        provider, facility = self._select_provider(doc_spec)

        # Determine if this is an employment records subpoena
        is_employment = "EMPLOYMENT" in subtype

        # Cover sheet (page 1)
        story = self._build_cover_sheet(doc_spec, provider, facility, is_employment)

        # Add actual records behind the cover sheet
        if is_employment:
            story.append(PageBreak())
            story.extend(self._build_employment_records(doc_spec))
        else:
            story.append(PageBreak())
            story.extend(self._build_medical_records(doc_spec, provider, facility))

        return story

    # ------------------------------------------------------------------
    # Provider selection
    # ------------------------------------------------------------------

    def _select_provider(self, doc_spec: Any) -> tuple[Any, str]:
        """Pick a prior provider from case.prior_providers using round-robin index."""
        provider_index = doc_spec.context.get("provider_index") if doc_spec.context else None

        if provider_index is not None and self.case.prior_providers:
            idx = provider_index % len(self.case.prior_providers)
            provider = self.case.prior_providers[idx]
            return provider, provider.facility

        # Fallback: use treating physician for backward compatibility
        return self.case.treating_physician, self.case.treating_physician.facility

    # ------------------------------------------------------------------
    # Cover sheet (page 1)
    # ------------------------------------------------------------------

    def _build_cover_sheet(
        self, doc_spec: Any, provider: Any, facility: str, is_employment: bool = False
    ) -> list:
        """Build the custodian-declaration cover sheet."""
        story: list = []

        title = "RECORDS RECEIVED PURSUANT TO SUBPOENA"
        if is_employment:
            title = "EMPLOYMENT RECORDS RECEIVED PURSUANT TO SUBPOENA"

        story.append(Paragraph(title, self.styles["CenterBold"]))
        story.append(Spacer(1, 0.3 * inch))

        # Case caption
        case_caption = (
            f"<b>{self.case.applicant.full_name.upper()},</b><br/>"
            "<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Applicant,<br/>"
            "<br/>"
            "vs.<br/>"
            "<br/>"
            f"<b>{self.case.employer.company_name.upper()},</b><br/>"
            "<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Defendant."
        )
        story.append(Paragraph(case_caption, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.2 * inch))

        # ADJ number
        story.append(Paragraph(
            f"<b>ADJ No.: {self.case.injuries[0].adj_number}</b>",
            self.styles["BodyText14"],
        ))
        story.append(Spacer(1, 0.3 * inch))

        # Records produced by
        produced_by = facility if not is_employment else self.case.employer.company_name
        story.append(Paragraph("<b>RECORDS PRODUCED BY:</b>", self.styles["SectionHeader"]))
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph(produced_by, self.styles["BodyText14"]))
        if not is_employment:
            story.append(Paragraph(
                f"Provider: {provider.full_name} — {provider.specialty}",
                self.styles["SmallItalic"],
            ))
        story.append(Spacer(1, 0.2 * inch))

        # Date range — prior records use dates BEFORE DOI
        doi = self.case.injuries[0].date_of_injury
        records_start = doi - timedelta(days=random.randint(365, 1825))  # 1-5 years before
        records_end = doi - timedelta(days=random.randint(30, 90))  # 1-3 months before

        date_range_text = (
            f"<b>DATE RANGE OF RECORDS:</b><br/>"
            f"{records_start.strftime('%m/%d/%Y')} through {records_end.strftime('%m/%d/%Y')}"
        )
        story.append(Paragraph(date_range_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.2 * inch))

        # Custodian declaration
        custodian_names = [
            "Maria Rodriguez", "James Patterson", "Susan Chen",
            "Michael Anderson", "Jennifer Davis", "Patricia Nguyen",
            "Robert Kim", "Linda Garcia",
        ]
        custodian_name = random.choice(custodian_names)

        declaration_text = (
            "<b>CUSTODIAN OF RECORDS DECLARATION:</b><br/>"
            "<br/>"
            f"I, {custodian_name}, am the duly authorized custodian of records for {produced_by}. "
            "I hereby certify under penalty of perjury under the laws of the State of California that "
            f"the attached records are true and correct copies of records in the possession of {produced_by} "
            f"pertaining to {self.case.applicant.full_name}."
        )
        story.append(Paragraph(declaration_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.3 * inch))

        # Table of contents
        story.append(Paragraph(
            "<b>TABLE OF CONTENTS - RECORDS PRODUCED:</b>",
            self.styles["SectionHeader"],
        ))
        story.append(Spacer(1, 0.2 * inch))

        if is_employment:
            record_types = [
                ("Attendance Records", random.randint(2, 5)),
                ("Performance Reviews", random.randint(1, 3)),
                ("Job Description", 1),
                ("Personnel Action Forms", random.randint(1, 3)),
            ]
        else:
            record_types = [
                ("Office Visit Notes", random.randint(3, 8)),
                ("Progress Notes", random.randint(2, 6)),
                ("Imaging Reports", random.randint(1, 3)),
                ("Prescription/Medication Records", random.randint(1, 3)),
                ("Laboratory Test Results", random.randint(1, 3)),
                ("Referral Correspondence", random.randint(1, 2)),
            ]

        selected_records = random.sample(record_types, k=min(random.randint(4, 6), len(record_types)))
        selected_records.sort(key=lambda x: x[0])

        table_data = [["Record Type", "Pages"]]
        total_pages = 0
        for record_type, pages in selected_records:
            table_data.append([record_type, str(pages)])
            total_pages += pages
        table_data.append(["<b>TOTAL PAGES:</b>", f"<b>{total_pages}</b>"])

        col_widths = [4.5 * inch, 1.5 * inch]
        records_table = Table(table_data, colWidths=col_widths)
        records_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("FONTNAME", (0, 1), (-1, -2), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -2), 10),
            ("ALIGN", (0, 1), (0, -2), "LEFT"),
            ("ALIGN", (1, 1), (1, -2), "CENTER"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, -1), (-1, -1), 11),
            ("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey),
            ("ALIGN", (0, -1), (0, -1), "LEFT"),
            ("ALIGN", (1, -1), (1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))

        story.append(records_table)
        story.append(Spacer(1, 0.3 * inch))

        # Date received
        date_received = doc_spec.doc_date + timedelta(days=random.randint(14, 28))
        story.append(Paragraph(
            f"<b>DATE RECEIVED:</b> {date_received.strftime('%B %d, %Y')}",
            self.styles["BodyText14"],
        ))
        story.append(Spacer(1, 0.3 * inch))

        # Certification
        cert_text = (
            "<b>CERTIFICATION:</b><br/>"
            "<br/>"
            "I certify that the attached records are true and correct copies of the original records "
            "maintained by this facility. These records have been produced in response to a subpoena "
            "duces tecum issued in the above-referenced matter. The records are transmitted in "
            "accordance with California Evidence Code Section 1560 and related provisions."
        )
        story.append(Paragraph(cert_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.3 * inch))

        # Custodian signature
        story.append(Paragraph(
            f"DATED: {doc_spec.doc_date.strftime('%B %d, %Y')}",
            self.styles["BodyText14"],
        ))
        story.append(Spacer(1, 0.4 * inch))

        signature_text = (
            f"_______________________________<br/>"
            f"{custodian_name}<br/>"
            f"Custodian of Records<br/>"
            f"{produced_by}"
        )
        story.append(Paragraph(signature_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.3 * inch))

        # Privacy notice
        privacy_text = (
            "<i><b>PRIVACY NOTICE:</b> These records contain confidential medical information protected by "
            "state and federal privacy laws. Unauthorized disclosure or use of this information may subject "
            "you to civil or criminal penalties. These records should be handled, stored, and disposed of "
            "in accordance with applicable privacy regulations.</i>"
        )
        story.append(Paragraph(privacy_text, self.styles["SmallItalic"]))

        return story

    # ------------------------------------------------------------------
    # Medical records content (pages 2+)
    # ------------------------------------------------------------------

    def _build_medical_records(self, doc_spec: Any, provider: Any, facility: str) -> list:
        """Generate 3-8 pages of actual clinical content from a prior provider."""
        from data.content_pools import (
            MEDICATIONS_BY_SPECIALTY,
            get_exam_findings,
            get_prior_chief_complaint,
            get_treatment_narrative,
        )

        story: list = []
        doi = self.case.injuries[0].date_of_injury
        body_parts = self.case.injuries[0].body_parts if self.case.injuries else ["lumbar spine"]

        # Generate visit dates — all pre-DOI, sorted chronologically
        num_visits = random.randint(3, 6)
        visit_dates = self._generate_pre_doi_dates(doi, num_visits)

        # 2-4 office visit notes
        num_office_visits = min(random.randint(2, 4), len(visit_dates))
        for i in range(num_office_visits):
            if i > 0:
                story.append(PageBreak())
            story.extend(self._build_office_visit_note(
                provider, facility, visit_dates[i], body_parts, i == 0,
            ))

        # 1-3 progress notes
        num_progress = random.randint(1, 3)
        remaining_dates = visit_dates[num_office_visits:]
        for i in range(num_progress):
            story.append(PageBreak())
            pn_date = remaining_dates[i] if i < len(remaining_dates) else (
                doi - timedelta(days=random.randint(60, 300))
            )
            story.extend(self._build_progress_note(provider, facility, pn_date, body_parts))

        # 0-1 imaging report
        if random.random() < 0.7:
            story.append(PageBreak())
            img_date = doi - timedelta(days=random.randint(90, 730))
            story.extend(self._build_imaging_report(provider, facility, img_date, body_parts))

        # 0-1 medication list
        if random.random() < 0.6:
            story.append(PageBreak())
            med_date = doi - timedelta(days=random.randint(30, 180))
            story.extend(self._build_medication_list(provider, facility, med_date))

        return story

    def _generate_pre_doi_dates(self, doi: date, count: int) -> list[date]:
        """Generate sorted pre-DOI dates spanning 3 months to 5 years before injury."""
        min_days_before = 90
        max_days_before = 1825
        dates = []
        for _ in range(count):
            days_before = random.randint(min_days_before, max_days_before)
            dates.append(doi - timedelta(days=days_before))
        dates.sort()
        return dates

    def _mini_letterhead(self, provider: Any, facility: str, visit_date: date) -> list:
        """Generate a compact letterhead for a clinical record page."""
        elements = self.make_letterhead(facility, provider.address, provider.phone)
        elements.append(Paragraph(
            f"<b>{provider.full_name}</b> — {provider.specialty}",
            self.styles["BodyText14"],
        ))
        elements.append(Paragraph(
            f"NPI: {provider.npi} &nbsp;&nbsp; License: {provider.license_number}",
            self.styles["SmallItalic"],
        ))
        elements.append(Spacer(1, 0.1 * inch))
        elements.append(Paragraph(
            f"<b>Date of Service:</b> {visit_date.strftime('%B %d, %Y')}",
            self.styles["BodyText14"],
        ))
        elements.append(Spacer(1, 0.15 * inch))
        return elements

    def _build_office_visit_note(
        self, provider: Any, facility: str, visit_date: date,
        body_parts: list[str], is_initial: bool,
    ) -> list:
        """Build a 1-2 page office visit note."""
        from data.content_pools import get_exam_findings, get_prior_chief_complaint, get_treatment_narrative

        story: list = []

        # Mini letterhead
        story.extend(self._mini_letterhead(provider, facility, visit_date))

        # Patient header
        story.extend(self.make_patient_header())
        story.append(Spacer(1, 0.1 * inch))

        # Visit type
        visit_type = "INITIAL CONSULTATION" if is_initial else "OFFICE VISIT NOTE"
        story.append(Paragraph(f"<b>{visit_type}</b>", self.styles["SectionHeader"]))
        story.append(Spacer(1, 0.1 * inch))

        # Chief complaint
        story.append(Paragraph("<b>CHIEF COMPLAINT:</b>", self.styles["SectionHeader"]))
        cc = get_prior_chief_complaint(body_parts)
        story.append(Paragraph(cc, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.1 * inch))

        # History of Present Illness
        story.append(Paragraph("<b>HISTORY OF PRESENT ILLNESS:</b>", self.styles["SectionHeader"]))
        age = (visit_date - self.case.applicant.date_of_birth).days // 365
        gender_pronoun = random.choice(["He", "She"])
        hpi_templates = [
            f"This is a {age}-year-old {self.case.employer.position.lower()} who presents with "
            f"complaints of {body_parts[0]} pain. {gender_pronoun} reports the symptoms have been "
            f"present for approximately {random.randint(2, 24)} months. The pain is described as "
            f"{random.choice(['dull', 'aching', 'sharp', 'intermittent'])} and rated "
            f"{random.randint(3, 6)}/10. {gender_pronoun} denies any specific traumatic event.",
            f"Patient is a {age}-year-old individual presenting for evaluation of {body_parts[0]} "
            f"discomfort that has been gradually worsening over the past "
            f"{random.randint(1, 12)} months. Symptoms are exacerbated by "
            f"{random.choice(['prolonged sitting', 'lifting', 'repetitive motion', 'standing'])} "
            f"and partially relieved by rest and OTC medications.",
        ]
        story.append(Paragraph(random.choice(hpi_templates), self.styles["BodyText14"]))
        story.append(Spacer(1, 0.1 * inch))

        # Physical Examination
        story.append(Paragraph("<b>PHYSICAL EXAMINATION:</b>", self.styles["SectionHeader"]))
        exam_text = get_exam_findings(provider.specialty, body_parts, count=random.randint(5, 8))
        story.append(Paragraph(exam_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.1 * inch))

        # Assessment & Plan
        story.append(Paragraph("<b>ASSESSMENT AND PLAN:</b>", self.styles["SectionHeader"]))
        treatment_text = get_treatment_narrative("conservative", count=random.randint(2, 4))
        assessments = [
            f"1. {body_parts[0].title()} — {random.choice(['strain', 'degenerative changes', 'chronic pain syndrome', 'myofascial pain'])}",
            f"2. Continue current conservative management",
            f"3. Follow up in {random.choice(['4', '6', '8'])} weeks",
        ]
        if len(body_parts) > 1:
            assessments.insert(1, f"2. {body_parts[1].title()} — associated discomfort")
        for a in assessments:
            story.append(Paragraph(a, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.05 * inch))
        story.append(Paragraph(treatment_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.15 * inch))

        # Signature
        story.extend(self.make_signature_block(
            provider.full_name, provider.specialty, provider.license_number,
        ))

        return story

    def _build_progress_note(
        self, provider: Any, facility: str, note_date: date, body_parts: list[str],
    ) -> list:
        """Build a shorter progress note (0.5-1 page)."""
        story: list = []

        story.extend(self._mini_letterhead(provider, facility, note_date))
        story.extend(self.make_patient_header())

        story.append(Paragraph("<b>PROGRESS NOTE</b>", self.styles["SectionHeader"]))
        story.append(Spacer(1, 0.1 * inch))

        # Subjective
        story.append(Paragraph("<b>S:</b>", self.styles["SectionHeader"]))
        subjective_options = [
            f"Patient returns for follow-up. Reports {body_parts[0]} pain is "
            f"{random.choice(['stable', 'slightly improved', 'unchanged', 'mildly worse'])}. "
            f"Pain level {random.randint(3, 7)}/10. "
            f"{random.choice(['Sleeping well', 'Difficulty sleeping due to pain', 'Sleep is fair'])}.",
            f"Follow-up visit. Patient states {body_parts[0]} symptoms are "
            f"{random.choice(['manageable with medication', 'persistent but tolerable', 'slightly better since last visit'])}. "
            f"Denies new complaints.",
        ]
        story.append(Paragraph(random.choice(subjective_options), self.styles["BodyText14"]))
        story.append(Spacer(1, 0.1 * inch))

        # Objective
        story.append(Paragraph("<b>O:</b>", self.styles["SectionHeader"]))
        story.append(Paragraph(self.lorem_medical(sentences=random.randint(3, 5)), self.styles["BodyText14"]))
        story.append(Spacer(1, 0.1 * inch))

        # Assessment
        story.append(Paragraph("<b>A:</b>", self.styles["SectionHeader"]))
        story.append(Paragraph(
            f"{body_parts[0].title()} — {random.choice(['improving', 'stable', 'chronic', 'slow improvement'])}. "
            "Continue current treatment plan.",
            self.styles["BodyText14"],
        ))
        story.append(Spacer(1, 0.1 * inch))

        # Plan
        story.append(Paragraph("<b>P:</b>", self.styles["SectionHeader"]))
        plan_items = random.sample([
            "Continue current medications as prescribed.",
            "Physical therapy 2x/week for 4 weeks.",
            f"Follow up in {random.choice(['4', '6', '8'])} weeks.",
            "MRI recommended if symptoms do not improve.",
            "Referral to pain management for further evaluation.",
            "Home exercise program reviewed and updated.",
            "Continue activity modification as tolerated.",
            "Consider injection therapy if plateau persists.",
        ], k=random.randint(2, 4))
        for item in plan_items:
            story.append(Paragraph(f"- {item}", self.styles["BodyText14"]))

        story.append(Spacer(1, 0.15 * inch))
        story.extend(self.make_signature_block(
            provider.full_name, provider.specialty, provider.license_number,
        ))

        return story

    def _build_imaging_report(
        self, provider: Any, facility: str, report_date: date, body_parts: list[str],
    ) -> list:
        """Build a body-part-appropriate imaging report (0.5-1 page)."""
        story: list = []

        # Use imaging center name variant
        imaging_facility = random.choice([
            f"{facility} — Diagnostic Imaging",
            f"{facility.split()[0]} Diagnostic Imaging Center",
            facility,
        ])
        story.extend(self._mini_letterhead(provider, imaging_facility, report_date))
        story.extend(self.make_patient_header())

        body_part = body_parts[0]
        modality = self._select_modality(body_part)

        story.append(Paragraph(
            f"<b>{modality} — {body_part.upper()}</b>",
            self.styles["SectionHeader"],
        ))
        story.append(Spacer(1, 0.1 * inch))

        # Clinical indication
        story.append(Paragraph("<b>CLINICAL INDICATION:</b>", self.styles["SectionHeader"]))
        story.append(Paragraph(
            f"{body_part.title()} pain, evaluate for structural abnormality.",
            self.styles["BodyText14"],
        ))
        story.append(Spacer(1, 0.1 * inch))

        # Technique
        story.append(Paragraph("<b>TECHNIQUE:</b>", self.styles["SectionHeader"]))
        technique_text = self._imaging_technique(modality, body_part)
        story.append(Paragraph(technique_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.1 * inch))

        # Findings
        story.append(Paragraph("<b>FINDINGS:</b>", self.styles["SectionHeader"]))
        findings = self._imaging_findings(modality, body_part)
        for finding in findings:
            story.append(Paragraph(f"- {finding}", self.styles["BodyText14"]))
        story.append(Spacer(1, 0.1 * inch))

        # Impression
        story.append(Paragraph("<b>IMPRESSION:</b>", self.styles["SectionHeader"]))
        impressions = self._imaging_impression(body_part)
        for i, imp in enumerate(impressions, 1):
            story.append(Paragraph(f"{i}. {imp}", self.styles["BodyText14"]))

        story.append(Spacer(1, 0.15 * inch))

        # Radiologist signature
        radiologist_name = f"Dr. {self.case.treating_physician.last_name}"  # Reuse name gen
        story.extend(self.make_signature_block(
            provider.full_name, f"Interpreting Physician — {provider.specialty}",
            provider.license_number,
        ))

        return story

    def _select_modality(self, body_part: str) -> str:
        """Select an appropriate imaging modality for the body part."""
        if "spine" in body_part.lower():
            return random.choice(["MRI", "X-RAY", "CT SCAN"])
        elif "shoulder" in body_part.lower() or "knee" in body_part.lower():
            return random.choice(["MRI", "X-RAY"])
        elif "wrist" in body_part.lower() or "hand" in body_part.lower():
            return random.choice(["X-RAY", "MRI"])
        elif "hip" in body_part.lower():
            return random.choice(["X-RAY", "MRI", "CT SCAN"])
        else:
            return random.choice(["X-RAY", "MRI"])

    def _imaging_technique(self, modality: str, body_part: str) -> str:
        if modality == "MRI":
            return (
                f"Multiplanar, multisequence MRI of the {body_part} was performed without "
                "intravenous contrast. Sequences include T1-weighted, T2-weighted, STIR, "
                "and proton density images in axial, sagittal, and coronal planes."
            )
        elif modality == "CT SCAN":
            return (
                f"CT scan of the {body_part} was performed with thin axial sections "
                "and multiplanar reconstructions in sagittal and coronal planes. "
                "No intravenous contrast was administered."
            )
        else:
            return (
                f"Standard radiographic views of the {body_part} were obtained including "
                f"{random.choice(['AP and lateral', 'AP, lateral, and oblique', 'AP and oblique'])} projections."
            )

    def _imaging_findings(self, modality: str, body_part: str) -> list[str]:
        """Generate body-part-appropriate imaging findings."""
        spine_findings = [
            "Mild disc desiccation noted at multiple levels consistent with age-related degenerative changes.",
            "Small broad-based disc bulge without significant canal stenosis.",
            "Mild bilateral facet arthropathy with associated hypertrophy.",
            "No high-grade spinal canal or neuroforaminal stenosis identified.",
            "Vertebral body heights and alignment are maintained.",
            "Paraspinal soft tissues are unremarkable.",
            "Conus medullaris terminates at the expected level.",
        ]
        extremity_findings = [
            "No acute fracture or dislocation identified.",
            "Mild degenerative changes noted at the joint articulation.",
            "Soft tissues appear grossly unremarkable.",
            "No significant joint effusion appreciated.",
            "Ligamentous structures appear intact without signal abnormality.",
            "Mild tendinosis without evidence of full-thickness tear.",
            "Bone marrow signal intensity is within normal limits.",
        ]
        pool = spine_findings if "spine" in body_part.lower() else extremity_findings
        return random.sample(pool, min(random.randint(3, 5), len(pool)))

    def _imaging_impression(self, body_part: str) -> list[str]:
        """Generate imaging impression items."""
        impressions_pool = [
            f"Mild degenerative changes of the {body_part} without acute abnormality.",
            "No evidence of acute fracture or dislocation.",
            f"Age-appropriate degenerative changes of the {body_part}.",
            "Clinical correlation recommended.",
        ]
        return random.sample(impressions_pool, min(random.randint(2, 3), len(impressions_pool)))

    def _build_medication_list(
        self, provider: Any, facility: str, list_date: date,
    ) -> list:
        """Build a medication list table (0.5 page)."""
        from data.content_pools import MEDICATIONS_BY_SPECIALTY

        story: list = []

        story.extend(self._mini_letterhead(provider, facility, list_date))
        story.extend(self.make_patient_header())

        story.append(Paragraph("<b>CURRENT MEDICATION LIST</b>", self.styles["SectionHeader"]))
        story.append(Spacer(1, 0.15 * inch))

        # Get medications for provider's specialty
        meds = MEDICATIONS_BY_SPECIALTY.get(
            provider.specialty,
            MEDICATIONS_BY_SPECIALTY.get("Internal Medicine", []),
        )
        selected_meds = random.sample(meds, min(random.randint(3, 5), len(meds)))

        table_data = [["Medication", "Dosage", "Frequency"]]
        for med_name, dosage, frequency in selected_meds:
            table_data.append([med_name, dosage, frequency])

        med_table = Table(table_data, colWidths=[2.5 * inch, 1.5 * inch, 2.5 * inch])
        med_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            *[("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f8f9fa"))
              for i in range(2, len(table_data), 2)],
        ]))

        story.append(med_table)
        story.append(Spacer(1, 0.2 * inch))

        story.append(Paragraph(
            "<b>Allergies:</b> " + random.choice([
                "NKDA (No Known Drug Allergies)",
                "Penicillin — rash",
                "Sulfa drugs — hives",
                "NKDA",
                "Codeine — nausea",
            ]),
            self.styles["BodyText14"],
        ))

        story.append(Spacer(1, 0.15 * inch))
        story.extend(self.make_signature_block(
            provider.full_name, provider.specialty, provider.license_number,
        ))

        return story

    # ------------------------------------------------------------------
    # Employment records content
    # ------------------------------------------------------------------

    def _build_employment_records(self, doc_spec: Any) -> list:
        """Generate 2-4 pages of employment records."""
        story: list = []
        employer = self.case.employer
        applicant = self.case.applicant
        doi = self.case.injuries[0].date_of_injury

        # Attendance summary
        story.append(Paragraph(
            f"<b>{employer.company_name.upper()}</b>",
            self.styles["Letterhead"],
        ))
        story.append(Paragraph(
            f"{employer.address_street}, {employer.address_city}, CA {employer.address_zip}",
            self.styles["LetterheadSub"],
        ))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#333333")))
        story.append(Spacer(1, 0.15 * inch))

        story.append(Paragraph("<b>ATTENDANCE RECORD SUMMARY</b>", self.styles["SectionHeader"]))
        story.append(Paragraph(
            f"Employee: {applicant.full_name} &nbsp;&nbsp; Position: {employer.position} &nbsp;&nbsp; "
            f"Hire Date: {employer.hire_date.strftime('%m/%d/%Y')}",
            self.styles["BodyText14"],
        ))
        story.append(Spacer(1, 0.15 * inch))

        # Generate attendance data for 6 months before DOI
        months_data = []
        for m in range(6):
            month_date = doi - timedelta(days=30 * (6 - m))
            days_worked = random.randint(18, 22)
            absences = random.randint(0, 3)
            tardies = random.randint(0, 2)
            months_data.append([
                month_date.strftime("%B %Y"), str(days_worked),
                str(absences), str(tardies),
            ])

        att_table_data = [["Month", "Days Worked", "Absences", "Tardies"]] + months_data
        att_table = Table(att_table_data, colWidths=[2.0 * inch, 1.5 * inch, 1.5 * inch, 1.5 * inch])
        att_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            *[("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f8f9fa"))
              for i in range(2, len(att_table_data), 2)],
        ]))
        story.append(att_table)
        story.append(Spacer(1, 0.3 * inch))

        # Performance review excerpt
        story.append(PageBreak())
        story.append(Paragraph(
            f"<b>{employer.company_name.upper()}</b>",
            self.styles["Letterhead"],
        ))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#333333")))
        story.append(Spacer(1, 0.15 * inch))

        review_date = doi - timedelta(days=random.randint(90, 365))
        story.append(Paragraph("<b>ANNUAL PERFORMANCE REVIEW</b>", self.styles["SectionHeader"]))
        story.append(Paragraph(
            f"Employee: {applicant.full_name} &nbsp;&nbsp; Review Period: "
            f"{(review_date - timedelta(days=365)).strftime('%m/%d/%Y')} — {review_date.strftime('%m/%d/%Y')}",
            self.styles["BodyText14"],
        ))
        story.append(Spacer(1, 0.15 * inch))

        rating = random.choice(["Meets Expectations", "Exceeds Expectations", "Meets Expectations", "Satisfactory"])
        categories = [
            ("Job Knowledge", random.choice(["Satisfactory", "Good", "Excellent"])),
            ("Quality of Work", random.choice(["Satisfactory", "Good", "Excellent"])),
            ("Attendance & Punctuality", random.choice(["Satisfactory", "Good", "Needs Improvement"])),
            ("Teamwork", random.choice(["Good", "Excellent", "Satisfactory"])),
            ("Safety Compliance", random.choice(["Good", "Excellent", "Satisfactory"])),
        ]

        review_table_data = [["Category", "Rating"]]
        for cat, rat in categories:
            review_table_data.append([cat, rat])
        review_table_data.append(["<b>Overall Rating</b>", f"<b>{rating}</b>"])

        review_table = Table(review_table_data, colWidths=[3.5 * inch, 3.0 * inch])
        review_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8e8e8")),
            *[("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f8f9fa"))
              for i in range(2, len(review_table_data) - 1, 2)],
        ]))
        story.append(review_table)
        story.append(Spacer(1, 0.2 * inch))

        story.append(Paragraph("<b>Supervisor Comments:</b>", self.styles["SectionHeader"]))
        comments = random.choice([
            f"{applicant.first_name} is a reliable employee who consistently meets job requirements. "
            "Demonstrates good understanding of safety protocols and works well with team members.",
            f"{applicant.first_name} has shown steady improvement throughout the review period. "
            "Attendance has been acceptable. Recommend continued development in current role.",
            f"{applicant.first_name} performs duties satisfactorily and follows established procedures. "
            "Good communication skills and maintains positive working relationships.",
        ])
        story.append(Paragraph(comments, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.3 * inch))

        # Job description
        story.append(PageBreak())
        story.append(Paragraph(
            f"<b>{employer.company_name.upper()}</b>",
            self.styles["Letterhead"],
        ))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#333333")))
        story.append(Spacer(1, 0.15 * inch))

        story.append(Paragraph("<b>JOB DESCRIPTION</b>", self.styles["SectionHeader"]))
        story.append(Paragraph(
            f"<b>Position:</b> {employer.position} &nbsp;&nbsp; "
            f"<b>Department:</b> {employer.department}",
            self.styles["BodyText14"],
        ))
        story.append(Spacer(1, 0.1 * inch))

        story.append(Paragraph("<b>Essential Functions:</b>", self.styles["SectionHeader"]))
        functions = random.sample([
            "Perform assigned tasks in accordance with established procedures and safety guidelines.",
            "Operate equipment and machinery as required by position.",
            "Lift, carry, and move materials weighing up to 50 pounds.",
            "Stand, walk, bend, stoop, and reach throughout the workday.",
            "Maintain work area in clean and orderly condition.",
            "Complete required documentation and reports accurately.",
            "Communicate effectively with supervisors and coworkers.",
            "Follow all workplace safety protocols and report hazards.",
            "Attend required training sessions and safety meetings.",
            "Perform other duties as assigned by supervisor.",
        ], k=random.randint(5, 8))
        for i, func in enumerate(functions, 1):
            story.append(Paragraph(f"{i}. {func}", self.styles["BodyText14"]))

        story.append(Spacer(1, 0.15 * inch))
        story.append(Paragraph("<b>Physical Requirements:</b>", self.styles["SectionHeader"]))
        phys_reqs = [
            f"Standing/Walking: {random.choice(['6-8', '4-6', '2-4'])} hours per day",
            f"Lifting: Up to {random.choice(['25', '50', '75'])} lbs {random.choice(['occasionally', 'frequently'])}",
            f"Bending/Stooping: {random.choice(['Frequent', 'Occasional', 'Regular'])}",
            f"Repetitive Motion: {random.choice(['Frequent', 'Occasional', 'Continuous'])}",
        ]
        for req in phys_reqs:
            story.append(Paragraph(f"- {req}", self.styles["BodyText14"]))

        return story
