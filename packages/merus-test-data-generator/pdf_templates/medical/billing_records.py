"""
Medical Billing Records Template

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import random
from datetime import timedelta
from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from data.wc_constants import CPT_CODES


class BillingRecords(BaseTemplate):
    """Medical billing and charges statement"""

    def build_story(self, doc_spec):
        """Build 1-2 page medical billing records"""
        story = []

        # Provider billing header
        provider_name = self.case.treating_physician.full_name
        story.extend(self.make_letterhead(
            f"{provider_name} Medical Group",
            self.case.treating_physician.address,
            self.case.treating_physician.phone
        ))
        story.append(Spacer(1, 0.3*inch))

        # Patient and claim reference
        story.extend(self.make_patient_header())
        story.append(Spacer(1, 0.2*inch))
        story.extend(self.make_claim_reference_block())
        story.append(Spacer(1, 0.3*inch))

        # Title
        story.append(Paragraph("<b>STATEMENT OF CHARGES</b>", self.styles['CenterBold']))
        story.append(Spacer(1, 0.2*inch))

        # Statement details
        story.append(Paragraph(
            f"<b>Statement Date:</b> {doc_spec.doc_date.strftime('%B %d, %Y')}",
            self.styles['BodyText14']
        ))
        story.append(Paragraph(
            f"<b>Billing Period:</b> {self.case.timeline.date_first_treatment.strftime('%m/%d/%Y')} - "
            f"{doc_spec.doc_date.strftime('%m/%d/%Y')}",
            self.styles['BodyText14']
        ))
        story.append(Paragraph(
            f"<b>Provider Tax ID:</b> {random.randint(10, 99)}-{random.randint(1000000, 9999999)}",
            self.styles['BodyText14']
        ))
        story.append(Spacer(1, 0.3*inch))

        # Billing table
        # Select 5-10 line items from CPT codes (flatten nested dict)
        all_cpts = [(code, desc) for cat_list in CPT_CODES.values() for code, desc in cat_list]
        selected_cpts = random.sample(all_cpts, k=min(random.randint(5, 10), len(all_cpts)))

        billing_data = [["Date of Service", "CPT Code", "Description", "Units", "Charge", "Provider"]]

        total_charges = 0.0
        date_range_days = (doc_spec.doc_date - self.case.timeline.date_first_treatment).days

        for idx, (cpt_code, description) in enumerate(selected_cpts):
            # Generate service date spread across treatment period
            days_offset = int(date_range_days * (idx / len(selected_cpts)))
            service_date = self.case.timeline.date_first_treatment + timedelta(days=days_offset)

            # Generate realistic charges based on service type
            if any(word in description.lower() for word in ['evaluation', 'consultation', 'office visit']):
                charge = random.uniform(150.0, 400.0)
            elif any(word in description.lower() for word in ['surgery', 'procedure', 'operative']):
                charge = random.uniform(2000.0, 8000.0)
            elif any(word in description.lower() for word in ['therapy', 'rehabilitation']):
                charge = random.uniform(100.0, 250.0)
            elif any(word in description.lower() for word in ['injection', 'injection']):
                charge = random.uniform(200.0, 600.0)
            elif any(word in description.lower() for word in ['imaging', 'x-ray', 'mri', 'ct']):
                charge = random.uniform(400.0, 2500.0)
            else:
                charge = random.uniform(150.0, 1000.0)

            units = random.choice([1, 1, 1, 1, 2, 3])  # Most services are 1 unit
            line_total = charge * units
            total_charges += line_total

            # Truncate long descriptions
            display_desc = description if len(description) <= 45 else description[:42] + "..."

            billing_data.append([
                service_date.strftime('%m/%d/%Y'),
                cpt_code,
                display_desc,
                str(units),
                f"${charge:.2f}",
                provider_name.split()[-1]  # Last name only
            ])

        # Sort by date
        billing_data[1:] = sorted(billing_data[1:], key=lambda x: x[0])

        # Create billing table
        billing_table = Table(
            billing_data,
            colWidths=[0.9*inch, 0.8*inch, 2.2*inch, 0.5*inch, 0.8*inch, 1.3*inch]
        )
        billing_table.setStyle(TableStyle([
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
            ('ALIGN', (3, 1), (3, -1), 'CENTER'),  # Units
            ('ALIGN', (4, 1), (4, -1), 'RIGHT'),   # Charges
        ]))

        story.append(billing_table)
        story.append(Spacer(1, 0.3*inch))

        # Total and balance section
        story.append(self.make_hr())
        story.append(Spacer(1, 0.2*inch))

        # Calculate payment info
        payments_received = random.uniform(0, total_charges * 0.3)  # 0-30% paid
        balance_due = total_charges - payments_received

        summary_data = [
            ["", ""],
            ["Total Charges:", f"${total_charges:.2f}"],
            ["Payments Received:", f"${payments_received:.2f}"],
            ["", ""],
        ]

        summary_table = Table(summary_data, colWidths=[4.5*inch, 1.5*inch])
        summary_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))

        story.append(summary_table)

        # Balance due (highlighted)
        balance_data = [["BALANCE DUE:", f"${balance_due:.2f}"]]
        balance_table = Table(balance_data, colWidths=[4.5*inch, 1.5*inch])
        balance_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 14),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#CC0000')),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LINEABOVE', (0, 0), (-1, 0), 2, colors.black),
        ]))

        story.append(balance_table)
        story.append(Spacer(1, 0.4*inch))

        # Payment information
        payment_info = (
            "<b>PAYMENT INFORMATION</b>\n\n"
            "This is a workers' compensation claim. Payment should be remitted by the claims administrator.\n\n"
            f"<b>Claims Administrator:</b> {self.case.insurance.carrier_name}\n"
            f"<b>Claim Number:</b> {self.case.insurance.claim_number}\n"
            f"<b>Adjuster:</b> {self.case.insurance.adjuster_name}\n"
            f"<b>Adjuster Phone:</b> {self.case.insurance.adjuster_phone}\n\n"
            "All charges are in accordance with the Official Medical Fee Schedule (OMFS) for California Workers' Compensation."
        )

        story.append(Paragraph(payment_info, self.styles['BodyText14']))
        story.append(Spacer(1, 0.3*inch))

        # Billing contact
        story.append(Paragraph(
            f"<i>For billing questions, please contact our office at {self.case.treating_physician.phone}</i>",
            self.styles['SmallItalic']
        ))
        story.append(Spacer(1, 0.2*inch))

        # Provider signature
        story.extend(self.make_signature_block(
            f"Billing Department",
            f"{provider_name} Medical Group",
            f"Statement #{random.randint(100000, 999999)}"
        ))

        return story
