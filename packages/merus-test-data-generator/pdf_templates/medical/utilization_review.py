"""
Utilization Review Decision Template

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import random
from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from data.wc_constants import CPT_CODES


class UtilizationReview(BaseTemplate):
    """Utilization Review decision letter"""

    def build_story(self, doc_spec):
        """Build 2-3 page UR decision"""
        story = []

        # UR organization letterhead
        ur_org = "California Utilization Review Services"
        story.extend(self.make_letterhead(
            ur_org,
            f"{random.randint(100, 9999)} Professional Plaza\nSuite {random.randint(100, 999)}\n"
            f"Sacramento, CA 9582{random.randint(0, 9)}",
            f"({random.randint(800, 888)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"
        ))
        story.append(Spacer(1, 0.3*inch))

        # Patient and claim information
        story.append(Paragraph("<b>UTILIZATION REVIEW DECISION</b>", self.styles['CenterBold']))
        story.append(Spacer(1, 0.2*inch))

        info_data = [
            ["Patient Name:", f"{self.case.applicant.first_name} {self.case.applicant.last_name}"],
            ["Date of Birth:", self.case.applicant.date_of_birth.strftime('%m/%d/%Y')],
            ["Claim Number:", self.case.insurance.claim_number],
            ["Date of Injury:", self.case.timeline.date_of_injury.strftime('%m/%d/%Y')],
            ["Employer:", self.case.employer.company_name],
            ["Review Date:", doc_spec.doc_date.strftime('%m/%d/%Y')],
        ]

        info_table = Table(info_data, colWidths=[2*inch, 4*inch])
        info_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))

        story.append(info_table)
        story.append(Spacer(1, 0.3*inch))

        # Request details
        all_cpts = [(code, desc) for cat_list in CPT_CODES.values() for code, desc in cat_list]
        requested_procedures = random.sample(all_cpts, k=min(random.randint(1, 3), len(all_cpts)))
        procedure_list = "\n".join([f"• {code}: {desc}" for code, desc in requested_procedures])

        request_content = (
            f"<b>Requesting Physician:</b> {self.case.treating_physician.full_name}, {self.case.treating_physician.specialty}\n\n"
            f"<b>Treatment Requested:</b>\n{procedure_list}\n\n"
            f"<b>Date of Request:</b> {doc_spec.doc_date.strftime('%m/%d/%Y')}"
        )
        story.extend(self.make_section("REQUEST DETAILS", request_content))

        # ACOEM/MTUS guidelines reference
        guidelines_content = (
            "This utilization review was conducted in accordance with California Code of Regulations, Title 8, "
            "Section 9792.6 et seq., and applicable MTUS (Medical Treatment Utilization Schedule) guidelines. "
            f"The review considered the ACOEM (American College of Occupational and Environmental Medicine) "
            f"guidelines for {', '.join(self.case.injuries[0].body_parts).lower() if self.case.injuries else 'the injured body part'} injuries "
            "and relevant peer-reviewed medical literature."
        )
        story.extend(self.make_section("MEDICAL TREATMENT GUIDELINES", guidelines_content))

        # Clinical review
        clinical_review = self.lorem_medical(random.randint(4, 6))
        story.extend(self.make_section("CLINICAL REVIEW", clinical_review))

        # Decision (60% approved, 25% modified, 15% denied)
        decision_type = random.choices(
            ["APPROVED", "APPROVED WITH MODIFICATION", "DENIED"],
            weights=[60, 25, 15]
        )[0]

        if decision_type == "APPROVED":
            decision_content = (
                f"<b>DECISION: APPROVED</b>\n\n"
                f"The requested treatment is approved as medically necessary and consistent with established "
                f"treatment guidelines for the documented work-related condition. The treatment is reasonably "
                f"required to cure or relieve the effects of the industrial injury."
            )
        elif decision_type == "APPROVED WITH MODIFICATION":
            decision_content = (
                f"<b>DECISION: APPROVED WITH MODIFICATION</b>\n\n"
                f"The requested treatment is approved with the following modifications: "
                f"{random.choice(['reduced frequency of treatments', 'alternative procedure recommended', 'limited to 6 sessions initially with re-evaluation'])}. "
                f"The modification is based on MTUS guidelines and clinical appropriateness."
            )
        else:
            decision_content = (
                f"<b>DECISION: NOT MEDICALLY NECESSARY - DENIED</b>\n\n"
                f"The requested treatment is not approved at this time. The treatment "
                f"{'does not meet MTUS guidelines' if random.random() > 0.5 else 'is not supported by current clinical evidence'} "
                f"for the documented condition. "
                f"{'Alternative treatments should be considered' if random.random() > 0.5 else 'Further conservative care is recommended'}."
            )

        story.extend(self.make_section("DECISION", decision_content))

        # Rationale
        rationale_points = []
        if decision_type == "APPROVED":
            rationale_points.extend([
                "Medical records support the diagnosis and medical necessity of requested treatment",
                "Treatment is consistent with ACOEM guidelines and MTUS protocols",
                "Expected outcomes justify the proposed intervention",
                "Patient has failed or exhausted appropriate conservative treatments" if random.random() > 0.5 else "Treatment is appropriate at this stage of care"
            ])
        elif decision_type == "APPROVED WITH MODIFICATION":
            rationale_points.extend([
                "Core treatment request is reasonable but frequency/duration should be adjusted",
                "Modified approach aligns better with evidence-based guidelines",
                "Initial trial period appropriate to assess effectiveness"
            ])
        else:
            rationale_points.extend([
                "Insufficient evidence of medical necessity in documentation provided",
                "Treatment not consistent with MTUS guidelines for this condition",
                "Alternative treatment options should be explored first",
                "Additional diagnostic workup or conservative treatment recommended"
            ])

        rationale_content = "\n\n".join([f"• {point}" for point in rationale_points])
        story.extend(self.make_section("RATIONALE", rationale_content))

        # Appeal rights notice
        appeal_content = (
            "<b>IMPORTANT NOTICE OF APPEAL RIGHTS</b>\n\n"
            "If you disagree with this decision, you have the right to request an Independent Medical Review (IMR). "
            "You must submit your request within six (6) months of receipt of this decision. Your request must be "
            "submitted in writing to the Administrative Director, Division of Workers' Compensation, or you may "
            "contact your local Information and Assistance Officer.\n\n"
            "For IMR requests:\n"
            "• Phone: (800) 794-6900\n"
            "• Website: www.dir.ca.gov/dwc/IMR/IMR_Form_English.pdf\n\n"
            "This decision does not affect your right to file for a dispute resolution through the Workers' "
            "Compensation Appeals Board."
        )
        story.extend(self.make_section("APPEAL RIGHTS", appeal_content))

        # Reviewer signature
        reviewer_name = f"Dr. {random.choice(['Patricia', 'Richard', 'Elizabeth', 'William'])} "
        reviewer_name += random.choice(['Thompson', 'Garcia', 'Wilson', 'Davis'])

        story.append(Spacer(1, 0.4*inch))
        story.extend(self.make_signature_block(
            reviewer_name,
            "Medical Director, Utilization Review",
            f"CA License #{random.randint(10000, 99999)}"
        ))

        story.append(Spacer(1, 0.1*inch))
        story.append(Paragraph(
            f"<i>UR Decision Reference: UR{random.randint(100000, 999999)}</i>",
            self.styles['SmallItalic']
        ))

        return story
