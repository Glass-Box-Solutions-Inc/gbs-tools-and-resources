"""
Pharmacy Records Template

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import random
from datetime import timedelta
from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from data.wc_constants import MEDICATIONS


class PharmacyRecords(BaseTemplate):
    """Pharmacy prescription history log"""

    def build_story(self, doc_spec):
        """Build 1-3 page pharmacy records"""
        story = []

        # Pharmacy letterhead
        pharmacy_name = random.choice([
            "Pacific Coast Pharmacy",
            "California Care Pharmacy",
            "Bay Area Rx",
            "Premier Health Pharmacy"
        ])
        story.extend(self.make_letterhead(
            pharmacy_name,
            f"{random.randint(100, 9999)} Main Street\n"
            f"San Francisco, CA 9411{random.randint(0, 9)}",
            f"({random.randint(400, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"
        ))
        story.append(Spacer(1, 0.3*inch))

        # Patient header
        story.extend(self.make_patient_header())
        story.append(Spacer(1, 0.3*inch))

        # Title and date range
        story.append(Paragraph("<b>PRESCRIPTION HISTORY</b>", self.styles['CenterBold']))
        story.append(Spacer(1, 0.2*inch))

        date_range_start = self.case.timeline.date_first_treatment
        date_range_end = doc_spec.doc_date
        story.append(Paragraph(
            f"<b>Date Range:</b> {date_range_start.strftime('%m/%d/%Y')} - {date_range_end.strftime('%m/%d/%Y')}",
            self.styles['BodyText14']
        ))
        story.append(Paragraph(
            f"<b>Claim Number:</b> {self.case.insurance.claim_number}",
            self.styles['BodyText14']
        ))
        story.append(Spacer(1, 0.3*inch))

        # Prescription table
        selected_meds = random.sample(MEDICATIONS, k=random.randint(4, 8))

        # Table headers
        rx_data = [["Fill Date", "Drug Name", "Dosage", "Frequency", "Qty", "Prescriber", "Rx Number"]]

        # Generate prescription records with multiple fills
        total_charges = 0.0

        for med_name, med_dosage, med_freq in selected_meds:
            # Each medication may have 1-4 fills
            num_fills = random.randint(1, 4)
            dosage = med_dosage
            frequency = random.choice([
                "Take 1 tablet daily",
                "Take 1 tablet twice daily",
                "Take 1-2 tablets every 4-6 hours as needed",
                "Take 1 tablet three times daily",
                "Take 1 tablet at bedtime",
                "Take 1 tablet every 8 hours"
            ])
            prescriber = self.case.treating_physician.last_name  # Last name only

            for fill_num in range(num_fills):
                # Space fills out over time
                days_offset = int((date_range_end - date_range_start).days * (fill_num / num_fills))
                fill_date = date_range_start + timedelta(days=days_offset)

                quantity = random.choice([30, 60, 90, 120])
                rx_number = f"RX{random.randint(100000, 999999)}"

                rx_data.append([
                    fill_date.strftime('%m/%d/%Y'),
                    med_name,
                    dosage,
                    frequency,
                    str(quantity),
                    prescriber,
                    rx_number
                ])

                # Calculate charge
                total_charges += random.uniform(15.0, 250.0)

        # Sort by date
        rx_data[1:] = sorted(rx_data[1:], key=lambda x: x[0])

        # Create table
        rx_table = Table(rx_data, colWidths=[0.85*inch, 1.6*inch, 0.75*inch, 1.5*inch, 0.5*inch, 0.9*inch, 0.9*inch])
        rx_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#003366')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (4, 1), (4, -1), 'CENTER'),  # Qty column centered
        ]))

        story.append(rx_table)
        story.append(Spacer(1, 0.3*inch))

        # Summary section
        story.append(self.make_hr())
        story.append(Spacer(1, 0.2*inch))

        summary_data = [
            ["Total Prescriptions Filled:", str(len(rx_data) - 1)],
            ["Unique Medications:", str(len(selected_meds))],
            ["Total Pharmacy Charges:", f"${total_charges:.2f}"],
        ]

        summary_table = Table(summary_data, colWidths=[2.5*inch, 1.5*inch])
        summary_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))

        story.append(summary_table)
        story.append(Spacer(1, 0.3*inch))

        # Pharmacy certification
        story.append(Paragraph(
            "<i>This is a certified true and correct copy of pharmacy records for the above-named patient "
            "for the specified date range. All prescriptions were filled in accordance with California "
            "State Board of Pharmacy regulations.</i>",
            self.styles['SmallItalic']
        ))
        story.append(Spacer(1, 0.3*inch))

        # Pharmacist signature
        pharmacist_name = f"{random.choice(['James', 'Susan', 'Michael', 'Karen'])} "
        pharmacist_name += random.choice(['Chen', 'Miller', 'Nguyen', 'Brown'])

        story.extend(self.make_signature_block(
            pharmacist_name,
            "Pharmacist in Charge",
            f"CA RPh #{random.randint(10000, 99999)}"
        ))

        return story
