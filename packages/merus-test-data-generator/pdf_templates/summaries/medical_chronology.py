"""
Medical Chronology Template

Generates a detailed medical chronology/timeline document for Workers' Compensation cases.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import random
from datetime import timedelta
from data.wc_constants import ICD10_CODES, DEFAULT_ICD10


class MedicalChronology(BaseTemplate):
    """Medical chronology template showing timeline of medical treatment."""

    def build_story(self, doc_spec):
        """Build the medical chronology document."""
        story = []

        # Law firm letterhead
        story.extend(self.make_letterhead(
            "Adjudica Legal Services",
            "123 Legal Plaza, Suite 400, Los Angeles, CA 90012",
            "(213) 555-0100"
        ))
        story.append(Spacer(1, 0.3 * inch))

        # Title
        title = Paragraph("MEDICAL CHRONOLOGY", self.styles['CenterBold'])
        story.append(title)
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
            story.append(Paragraph(line, self.styles['BodyText14']))

        story.append(Spacer(1, 0.1 * inch))

        # Prepared by line
        prepared_line = f"<i>Prepared by: Adjudica Legal Services — {doc_spec.doc_date.strftime('%B %d, %Y')}</i>"
        story.append(Paragraph(prepared_line, self.styles['SmallItalic']))
        story.append(Spacer(1, 0.2 * inch))

        # Generate chronological entries
        entries = self._generate_chronology_entries(doc_spec.doc_date)

        # Build chronology table
        table_data = [['Date', 'Provider/Facility', 'Event Type', 'Description', 'Body Part(s)']]

        for entry in entries:
            table_data.append([
                entry['date'].strftime('%m/%d/%Y'),
                entry['provider'],
                entry['event_type'],
                entry['description'],
                entry['body_parts']
            ])

        # Create table with styling
        col_widths = [0.9*inch, 1.4*inch, 1.1*inch, 2.5*inch, 1.1*inch]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)

        table_style = TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),

            # Data rows
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 1), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 5),

            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),

            # Alternating row colors
            *[('BACKGROUND', (0, i), (-1, i), colors.HexColor('#f8f9fa'))
              for i in range(2, len(table_data), 2)]
        ])

        table.setStyle(table_style)
        story.append(table)
        story.append(Spacer(1, 0.3 * inch))

        # Summary section
        story.append(self.make_hr())
        story.append(Spacer(1, 0.1 * inch))

        summary_title = Paragraph("<b>CHRONOLOGY SUMMARY</b>", self.styles['SectionHeader'])
        story.append(summary_title)
        story.append(Spacer(1, 0.1 * inch))

        # Get unique providers
        providers = set(entry['provider'] for entry in entries if 'Dr.' in entry['provider'])

        # Get diagnoses from ICD-10 codes
        diagnoses = []
        for body_part in self.case.injuries[0].body_parts:
            body_part_lower = body_part.lower()
            if body_part_lower in ICD10_CODES:
                codes = ICD10_CODES[body_part_lower]
                # Pick first code as primary diagnosis
                if codes:
                    diagnoses.append(codes[0][1])

        if not diagnoses:
            diagnoses = [DEFAULT_ICD10[0][1]]

        summary_lines = [
            f"<b>Total Medical Encounters:</b> {len(entries)}",
            f"<b>Providers Seen:</b> {', '.join(sorted(providers))}",
            f"<b>Key Diagnoses:</b> {'; '.join(diagnoses)}",
            f"<b>Current Status:</b> {self._get_current_status()}",
        ]

        for line in summary_lines:
            story.append(Paragraph(line, self.styles['BodyText14']))
            story.append(Spacer(1, 0.05 * inch))

        story.append(Spacer(1, 0.2 * inch))

        # Preparer signature
        story.extend(self.make_signature_block(
            "Legal Assistant",
            "Adjudica Legal Services",
            None
        ))

        return story

    def _generate_chronology_entries(self, doc_date):
        """Generate realistic chronology entries from DOI to document date."""
        entries = []

        # Start from DOI
        current_date = self.case.injuries[0].date_of_injury
        treating_doc = self.case.treating_physician.full_name
        treating_facility = self.case.treating_physician.facility

        # Additional provider names for variety
        other_providers = [
            f"Dr. {random.choice(['Martinez', 'Johnson', 'Lee', 'Patel'])}",
            f"Dr. {random.choice(['Williams', 'Garcia', 'Chen', 'Rodriguez'])}"
        ]

        body_parts = ', '.join(self.case.injuries[0].body_parts)
        injury_type = self.case.injuries[0].injury_type.value.replace('_', ' ')

        # Initial ER visit
        entries.append({
            'date': current_date,
            'provider': 'Emergency Department',
            'event_type': 'Initial Treatment',
            'description': f'Initial evaluation and treatment for work-related {injury_type}. X-rays performed.',
            'body_parts': body_parts
        })

        # First follow-up (3-7 days later)
        current_date += timedelta(days=random.randint(3, 7))
        entries.append({
            'date': current_date,
            'provider': treating_doc,
            'event_type': 'Office Visit',
            'description': 'Follow-up examination. Prescribed pain medication and restricted work duties.',
            'body_parts': body_parts
        })

        # Generate entries throughout timeline
        visit_count = random.randint(15, 30)
        time_span = (doc_date - current_date).days

        for i in range(visit_count - 2):  # Already added 2 entries
            # Spread visits somewhat evenly but with realistic variation
            days_to_add = random.randint(
                int(time_span / visit_count * 0.5),
                int(time_span / visit_count * 1.5)
            )
            current_date += timedelta(days=days_to_add)

            if current_date > doc_date:
                break

            # Choose event type based on timeline progression
            progress = (current_date - self.case.injuries[0].date_of_injury).days / time_span

            if progress < 0.3:
                # Early treatment phase
                event_types = [
                    ('Office Visit', f'{treating_doc}', f'Ongoing treatment. Pain level assessed. Medications adjusted.'),
                    ('Physical Therapy', f'{treating_facility} PT Dept', 'Physical therapy session. Range of motion exercises.'),
                    ('Diagnostic Imaging', 'Imaging Center', 'MRI ordered to assess extent of injury.'),
                ]
            elif progress < 0.6:
                # Mid treatment phase
                event_types = [
                    ('Office Visit', f'{treating_doc}', 'Progress evaluation. Continued restricted work duties.'),
                    ('Physical Therapy', f'{treating_facility} PT Dept', 'PT session. Strengthening exercises initiated.'),
                    ('Specialist Consult', random.choice(other_providers), 'Specialist consultation regarding treatment plan.'),
                    ('Injection', f'{treating_doc}', 'Therapeutic injection administered for pain management.'),
                ]
            else:
                # Later treatment phase
                event_types = [
                    ('Office Visit', f'{treating_doc}', 'Follow-up examination. Discussing permanency and work restrictions.'),
                    ('Office Visit', random.choice(other_providers), 'Second opinion evaluation.'),
                    ('Physical Therapy', f'{treating_facility} PT Dept', 'Continued physical therapy. Functional capacity improving.'),
                ]

            # Special events
            if self.case.timeline.date_qme_evaluation and abs((current_date - self.case.timeline.date_qme_evaluation).days) < 3:
                if self.case.qme_physician:
                    entries.append({
                        'date': self.case.timeline.date_qme_evaluation,
                        'provider': self.case.qme_physician.full_name,
                        'event_type': 'QME Evaluation',
                        'description': 'Qualified Medical Evaluation. Comprehensive examination and review of medical records.',
                        'body_parts': body_parts
                    })
                    continue

            event = random.choice(event_types)
            entries.append({
                'date': current_date,
                'provider': event[1],
                'event_type': event[0],
                'description': event[2],
                'body_parts': body_parts
            })

        # Sort by date
        entries.sort(key=lambda x: x['date'])

        return entries

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
