"""
Medical Chronology Template — Enhanced with richer visit descriptions.

Generates 3-6 page medical chronologies with 25-50 visits, detailed per-event
descriptions from content pools, and a narrative summary.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import random
from datetime import timedelta

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from data.content_pools import get_chronology_description
from data.wc_constants import DEFAULT_ICD10, ICD10_CODES
from pdf_templates.base_template import BaseTemplate


class MedicalChronology(BaseTemplate):
    """Medical chronology template showing timeline of medical treatment."""

    def build_story(self, doc_spec):
        """Build 3-6 page medical chronology with rich descriptions."""
        story = []

        # Law firm letterhead
        story.extend(self.make_letterhead(
            "Adjudica Legal Services",
            "123 Legal Plaza, Suite 400, Los Angeles, CA 90012",
            "(213) 555-0100",
        ))
        story.append(Spacer(1, 0.3 * inch))

        # Title
        story.append(Paragraph("MEDICAL CHRONOLOGY", self.styles["CenterBold"]))
        story.append(Spacer(1, 0.2 * inch))

        # Case info block
        case_info = [
            f"<b>Applicant:</b> {self.case.applicant.full_name}",
            f"<b>Date of Birth:</b> {self.case.applicant.date_of_birth.strftime('%m/%d/%Y')}",
            f"<b>Date of Injury:</b> {self.case.injuries[0].date_of_injury.strftime('%m/%d/%Y')}",
            f"<b>Employer:</b> {self.case.employer.company_name}",
            f"<b>Claim Number:</b> {self.case.insurance.claim_number}",
            f"<b>Body Part(s):</b> {', '.join(self.case.injuries[0].body_parts)}",
        ]
        for line in case_info:
            story.append(Paragraph(line, self.styles["BodyText14"]))

        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph(
            f"<i>Prepared by: Adjudica Legal Services — {doc_spec.doc_date.strftime('%B %d, %Y')}</i>",
            self.styles["SmallItalic"],
        ))
        story.append(Spacer(1, 0.2 * inch))

        # Generate chronological entries (25-50 visits)
        entries = self._generate_chronology_entries(doc_spec.doc_date)

        # Build chronology table
        table_data = [["Date", "Provider/Facility", "Event Type", "Description", "Body Part(s)"]]
        for entry in entries:
            table_data.append([
                entry["date"].strftime("%m/%d/%Y"),
                entry["provider"],
                entry["event_type"],
                entry["description"],
                entry["body_parts"],
            ])

        col_widths = [0.9 * inch, 1.4 * inch, 1.0 * inch, 2.6 * inch, 1.1 * inch]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            *[("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f8f9fa"))
              for i in range(2, len(table_data), 2)],
        ]))
        story.append(table)
        story.append(Spacer(1, 0.3 * inch))

        # Summary section (2-3 paragraphs)
        story.extend(self._build_narrative_summary(entries, doc_spec))

        # Preparer signature
        story.extend(self.make_signature_block("Legal Assistant", "Adjudica Legal Services", None))

        return story

    def _generate_chronology_entries(self, doc_date):
        """Generate 25-50 realistic chronology entries from DOI to doc date."""
        entries = []
        current_date = self.case.injuries[0].date_of_injury
        treating_doc = self.case.treating_physician.full_name
        treating_facility = self.case.treating_physician.facility
        body_parts = ", ".join(self.case.injuries[0].body_parts)
        bp_list = self.case.injuries[0].body_parts

        other_providers = [
            f"Dr. {random.choice(['Martinez', 'Johnson', 'Lee', 'Patel', 'Singh', 'Williams'])}",
            f"Dr. {random.choice(['Garcia', 'Chen', 'Rodriguez', 'Kim', 'Brown', 'Davis'])}",
        ]

        # Calculate time span and target visit count
        time_span = (doc_date - current_date).days
        if time_span <= 0:
            time_span = 180
        visit_count = min(random.randint(30, 55), max(30, time_span // 5))

        # 1. Initial ER visit
        entries.append({
            "date": current_date,
            "provider": "Emergency Department",
            "event_type": "Initial Treatment",
            "description": get_chronology_description(
                "initial_treatment", body_part=bp_list[0] if bp_list else "affected area",
            ),
            "body_parts": body_parts,
        })

        # 2. First follow-up
        current_date += timedelta(days=random.randint(3, 7))
        entries.append({
            "date": current_date,
            "provider": treating_doc,
            "event_type": "Office Visit",
            "description": get_chronology_description("office_visit"),
            "body_parts": body_parts,
        })

        # Track PT session counter
        pt_session = 1

        # Generate remaining entries
        for i in range(visit_count - 2):
            days_to_add = max(3, int(time_span / visit_count * random.uniform(0.5, 1.5)))
            current_date += timedelta(days=days_to_add)
            if current_date > doc_date:
                break

            progress = (current_date - self.case.injuries[0].date_of_injury).days / time_span

            # Check for QME eval
            if (self.case.timeline.date_qme_evaluation and self.case.qme_physician
                    and abs((current_date - self.case.timeline.date_qme_evaluation).days) < 3):
                entries.append({
                    "date": self.case.timeline.date_qme_evaluation,
                    "provider": self.case.qme_physician.full_name,
                    "event_type": "QME Evaluation",
                    "description": (
                        "Qualified Medical Evaluation performed. Comprehensive examination, "
                        "review of medical records, and impairment rating assessment."
                    ),
                    "body_parts": body_parts,
                })
                continue

            # Check for UR dispute
            if (self.case.timeline.date_ur_dispute
                    and abs((current_date - self.case.timeline.date_ur_dispute).days) < 5):
                entries.append({
                    "date": self.case.timeline.date_ur_dispute,
                    "provider": "UR Organization",
                    "event_type": "UR Decision",
                    "description": get_chronology_description("ur_dispute"),
                    "body_parts": body_parts,
                })
                continue

            # Select event type based on timeline phase
            if progress < 0.25:
                event_choices = [
                    ("Office Visit", treating_doc, "office_visit"),
                    ("Physical Therapy", f"{treating_facility} PT", "physical_therapy"),
                    ("Diagnostic Imaging", "Imaging Center", "diagnostic_imaging"),
                    ("Office Visit", treating_doc, "office_visit"),
                ]
            elif progress < 0.5:
                event_choices = [
                    ("Office Visit", treating_doc, "office_visit"),
                    ("Physical Therapy", f"{treating_facility} PT", "physical_therapy"),
                    ("Specialist Consult", random.choice(other_providers), "specialist_consult"),
                    ("Injection", treating_doc, "injection"),
                    ("Office Visit", treating_doc, "office_visit"),
                    ("Medication Change", treating_doc, "medication_change"),
                ]
            elif progress < 0.75:
                event_choices = [
                    ("Office Visit", treating_doc, "office_visit"),
                    ("Physical Therapy", f"{treating_facility} PT", "physical_therapy"),
                    ("Office Visit", random.choice(other_providers), "office_visit"),
                    ("Injection", treating_doc, "injection"),
                    ("Office Visit", treating_doc, "office_visit"),
                ]
            else:
                event_choices = [
                    ("Office Visit", treating_doc, "office_visit"),
                    ("Office Visit", random.choice(other_providers), "office_visit"),
                    ("Physical Therapy", f"{treating_facility} PT", "physical_therapy"),
                ]

            event_type, provider, desc_key = random.choice(event_choices)

            # Build description kwargs
            desc_kwargs = {
                "body_part": bp_list[0] if bp_list else "affected area",
            }
            if desc_key == "physical_therapy":
                desc_kwargs["session_num"] = str(pt_session)
                pt_session += 1

            entries.append({
                "date": current_date,
                "provider": provider,
                "event_type": event_type,
                "description": get_chronology_description(desc_key, **desc_kwargs),
                "body_parts": body_parts,
            })

        entries.sort(key=lambda x: x["date"])
        return entries

    def _build_narrative_summary(self, entries, doc_spec):
        """Build a 2-3 paragraph narrative summary after the chronology table."""
        elements = []
        elements.append(self.make_hr())
        elements.append(Spacer(1, 0.1 * inch))
        elements.append(Paragraph("<b>CHRONOLOGY SUMMARY</b>", self.styles["SectionHeader"]))
        elements.append(Spacer(1, 0.1 * inch))

        # Stats
        providers = set(e["provider"] for e in entries if "Dr." in e["provider"])
        pt_count = sum(1 for e in entries if e["event_type"] == "Physical Therapy")
        injection_count = sum(1 for e in entries if e["event_type"] == "Injection")

        # Diagnoses
        diagnoses = []
        for bp in self.case.injuries[0].body_parts:
            bp_lower = bp.lower()
            if bp_lower in ICD10_CODES:
                codes = ICD10_CODES[bp_lower]
                if codes:
                    diagnoses.append(codes[0][1])
        if not diagnoses:
            diagnoses = [DEFAULT_ICD10[0][1]]

        # Summary stats
        stats = [
            f"<b>Total Medical Encounters:</b> {len(entries)}",
            f"<b>Date Range:</b> {entries[0]['date'].strftime('%m/%d/%Y')} through {entries[-1]['date'].strftime('%m/%d/%Y')}",
            f"<b>Providers Seen:</b> {', '.join(sorted(providers))}",
            f"<b>Physical Therapy Sessions:</b> {pt_count}",
            f"<b>Injections/Procedures:</b> {injection_count}",
            f"<b>Key Diagnoses:</b> {'; '.join(diagnoses)}",
            f"<b>Current Status:</b> {self._get_current_status()}",
        ]
        for line in stats:
            elements.append(Paragraph(line, self.styles["BodyText14"]))
            elements.append(Spacer(1, 0.03 * inch))

        elements.append(Spacer(1, 0.15 * inch))

        # Narrative paragraph
        injury_type = self.case.injuries[0].injury_type.value.replace("_", " ")
        narrative = (
            f"This medical chronology documents the treatment course for {self.case.applicant.full_name}'s "
            f"work-related {injury_type} injury sustained on {self.case.injuries[0].date_of_injury.strftime('%B %d, %Y')} "
            f"while employed by {self.case.employer.company_name} as a {self.case.employer.position.lower()}. "
            f"The patient has received {len(entries)} documented medical encounters over the course of treatment, "
            f"including {pt_count} physical therapy sessions and {injection_count} injection procedures. "
            f"Treatment has been primarily provided by {self.case.treating_physician.full_name} "
            f"({self.case.treating_physician.specialty})."
        )
        elements.append(Paragraph(narrative, self.styles["BodyText14"]))
        elements.append(Spacer(1, 0.1 * inch))

        # Outcome narrative
        outcome = random.choice([
            "The treatment record demonstrates a pattern of ongoing symptoms with partial response "
            "to conservative and interventional treatment measures. The patient continues to require "
            "medical care for the industrial injury.",
            "Despite comprehensive treatment including physical therapy, medication management, and "
            "interventional procedures, the patient continues to experience significant functional "
            "limitations attributable to the industrial injury.",
            "The medical chronology reflects a complex treatment course with multiple treatment "
            "modalities utilized. The patient has shown gradual improvement but retains residual "
            "deficits consistent with permanent impairment.",
        ])
        elements.append(Paragraph(outcome, self.styles["BodyText14"]))
        elements.append(Spacer(1, 0.2 * inch))

        return elements

    def _get_current_status(self):
        """Determine current case status based on timeline."""
        if self.case.timeline.date_settlement_conference:
            return "Awaiting settlement conference resolution"
        elif self.case.timeline.date_dor_filed:
            return "Declaration of Readiness filed, awaiting trial"
        elif self.case.timeline.date_qme_evaluation:
            return "Post-QME evaluation, permanent and stationary"
        elif self.case.timeline.date_application_filed:
            return "Application filed, in active treatment"
        else:
            return "In active treatment phase"
