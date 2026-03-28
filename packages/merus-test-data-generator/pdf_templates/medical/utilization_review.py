"""
Utilization Review Decision Template — Variant-aware with MTUS citations.

Generates 2-4 page UR decisions with clinical rationale, MTUS/ACOEM guideline
citations, and variant handling for IMR, RFA, standard, and expedited reviews.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import random

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from data.content_pools import get_clinical_rationale, get_mtus_citations
from data.wc_constants import CPT_CODES
from pdf_templates.base_template import BaseTemplate


class UtilizationReview(BaseTemplate):
    """Utilization Review decision letter with MTUS clinical rationale."""

    def build_story(self, doc_spec):
        """Build 2-4 page UR decision with variant handling."""
        story = []
        variant = doc_spec.context.get("variant", "regular") if doc_spec.context else "regular"
        is_imr = "imr" in variant
        is_expedited = "expedited" in variant
        body_parts = self.case.injuries[0].body_parts if self.case.injuries else []

        # --- Letterhead ---
        if is_imr:
            org_name = "MAXIMUS Federal Services — Independent Medical Review"
            org_address = (
                f"P.O. Box 138009\nSacramento, CA 95813-8009"
            )
            org_phone = "(800) 275-1878"
        else:
            org_name = "California Utilization Review Services"
            org_address = (
                f"{random.randint(100, 9999)} Professional Plaza\n"
                f"Suite {random.randint(100, 999)}\n"
                f"Sacramento, CA 9582{random.randint(0, 9)}"
            )
            org_phone = f"({random.randint(800, 888)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"

        story.extend(self.make_letterhead(org_name, org_address, org_phone))
        story.append(Spacer(1, 0.3 * inch))

        # --- Title ---
        if is_imr:
            title = "INDEPENDENT MEDICAL REVIEW DETERMINATION"
        elif is_expedited:
            title = "EXPEDITED UTILIZATION REVIEW DECISION"
        else:
            title = "UTILIZATION REVIEW DECISION"
        story.append(Paragraph(f"<b>{title}</b>", self.styles["CenterBold"]))
        story.append(Spacer(1, 0.2 * inch))

        # --- Patient/claim info ---
        info_data = [
            ["Patient Name:", f"{self.case.applicant.first_name} {self.case.applicant.last_name}"],
            ["Date of Birth:", self.case.applicant.date_of_birth.strftime("%m/%d/%Y")],
            ["Claim Number:", self.case.insurance.claim_number],
            ["Date of Injury:", self.case.timeline.date_of_injury.strftime("%m/%d/%Y")],
            ["Employer:", self.case.employer.company_name],
            ["Carrier:", self.case.insurance.carrier_name],
            ["Review Date:", doc_spec.doc_date.strftime("%m/%d/%Y")],
            ["Review Type:", "Expedited" if is_expedited else ("IMR" if is_imr else "Standard")],
        ]
        info_table = Table(info_data, colWidths=[2 * inch, 4 * inch])
        info_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (0, -1), "RIGHT"),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 0.3 * inch))

        # --- Request Details ---
        story.extend(self._build_request_details(body_parts))

        # --- Guidelines Reference ---
        story.extend(self._build_guidelines_section(body_parts))

        # --- Clinical Review (3-4 paragraphs) ---
        story.extend(self._build_clinical_review(body_parts))

        # --- Decision ---
        decision_type = self._pick_decision(is_imr)
        story.extend(self._build_decision(decision_type, is_imr))

        # --- Rationale (6-8 points with citations) ---
        story.extend(self._build_rationale(decision_type, body_parts))

        # --- IMR-specific evidence section ---
        if is_imr:
            story.extend(self._build_imr_evidence())

        # --- Appeal Rights ---
        if not is_imr:
            story.extend(self._build_appeal_rights())

        # --- Reviewer Credentials ---
        story.extend(self._build_reviewer_signature(is_imr))

        return story

    def _build_request_details(self, body_parts):
        """Treatment request details with CPT codes."""
        elements = []
        all_cpts = [(code, desc) for cat_list in CPT_CODES.values() for code, desc in cat_list]
        requested = random.sample(all_cpts, k=min(random.randint(1, 3), len(all_cpts)))
        proc_list = "\n".join([f"• {code}: {desc}" for code, desc in requested])
        bp_str = ", ".join(body_parts).lower() if body_parts else "the injured body part"

        content = (
            f"<b>Requesting Physician:</b> {self.case.treating_physician.full_name}, "
            f"{self.case.treating_physician.specialty}\n\n"
            f"<b>Body Part(s):</b> {bp_str}\n\n"
            f"<b>Treatment Requested:</b>\n{proc_list}\n\n"
            f"<b>Date of Request:</b> {random.choice(['concurrent with', '3 days prior to', '5 days prior to'])} this review"
        )
        elements.extend(self.make_section("REQUEST DETAILS", content))
        return elements

    def _build_guidelines_section(self, body_parts):
        """MTUS/ACOEM guidelines reference."""
        elements = []
        citations = get_mtus_citations(body_parts, count=4)
        citations_text = "\n".join([f"• {c}" for c in citations])

        content = (
            "This utilization review was conducted in accordance with California Code of Regulations, "
            "Title 8, Section 9792.6 et seq., and the Medical Treatment Utilization Schedule (MTUS). "
            "The review considered the ACOEM (American College of Occupational and Environmental Medicine) "
            "Practice Guidelines and relevant peer-reviewed medical literature.\n\n"
            f"<b>Applicable MTUS Guidelines:</b>\n{citations_text}"
        )
        elements.extend(self.make_section("MEDICAL TREATMENT GUIDELINES", content))
        return elements

    def _build_clinical_review(self, body_parts):
        """Clinical review — 3-4 paragraphs, body-part-specific."""
        elements = []
        bp_str = ", ".join(body_parts[:2]).lower() if body_parts else "the affected area"

        paragraphs = [
            (
                f"Review of the submitted medical records reveals that the patient has been "
                f"receiving treatment for work-related injury to the {bp_str}. "
                f"The treating physician has documented ongoing symptoms and functional limitations."
            ),
            (
                f"The clinical documentation includes physical examination findings, "
                f"diagnostic imaging results, and treatment progress notes. "
                f"The patient's condition has been {random.choice(['gradually improving with current treatment', 'plateau in improvement despite ongoing treatment', 'showing mixed response to current treatment modality'])}."
            ),
            (
                f"Review of the treatment history indicates that the patient has "
                f"{random.choice(['completed an adequate trial of conservative treatment measures', 'not yet exhausted conservative treatment options', 'demonstrated partial response to initial treatment'])}. "
                f"The treating physician's rationale for the requested treatment has been considered."
            ),
            (
                f"Objective clinical findings {random.choice(['support', 'partially support', 'are inconclusive regarding'])} "
                f"the medical necessity of the requested treatment at this time. "
                f"The patient's functional status and treatment response have been evaluated against "
                f"evidence-based guidelines."
            ),
        ]

        content = "\n\n".join(random.sample(paragraphs, min(4, len(paragraphs))))
        elements.extend(self.make_section("CLINICAL REVIEW", content))
        return elements

    def _pick_decision(self, is_imr):
        """Pick decision type with appropriate probabilities."""
        if is_imr:
            # IMR upholds ~91% of UR denials
            return random.choices(
                ["UPHELD — NOT MEDICALLY NECESSARY", "OVERTURNED — APPROVED"],
                weights=[91, 9],
            )[0]
        return random.choices(
            ["APPROVED", "APPROVED WITH MODIFICATION", "DENIED"],
            weights=[60, 25, 15],
        )[0]

    def _build_decision(self, decision_type, is_imr):
        """Decision section with detailed rationale intro."""
        elements = []
        if "APPROVED" in decision_type and "MODIFICATION" not in decision_type and "OVERTURNED" not in decision_type:
            content = (
                f"<b>DECISION: APPROVED</b>\n\n"
                f"The requested treatment is approved as medically necessary and consistent with "
                f"the Medical Treatment Utilization Schedule (MTUS). The treatment is reasonably "
                f"required to cure or relieve the effects of the industrial injury per Labor Code §4600."
            )
        elif "MODIFICATION" in decision_type:
            modification = random.choice([
                "reduced frequency of treatments from 3x/week to 2x/week",
                "initial authorization of 6 sessions with re-evaluation required",
                "approved at lower intensity with step-up protocol if documented improvement",
                "limited to 4 weeks with formal progress evaluation before continuation",
            ])
            content = (
                f"<b>DECISION: APPROVED WITH MODIFICATION</b>\n\n"
                f"The requested treatment is approved with the following modifications: "
                f"{modification}. This modification aligns with MTUS guidelines and evidence-based "
                f"practice for the documented condition."
            )
        elif "OVERTURNED" in decision_type:
            content = (
                f"<b>DECISION: OVERTURNED — TREATMENT AUTHORIZED</b>\n\n"
                f"Upon independent medical review of all submitted evidence, the prior utilization "
                f"review denial is overturned. The requested treatment is determined to be medically "
                f"necessary and consistent with evidence-based guidelines. The treatment should be "
                f"authorized without further delay."
            )
        else:  # Denied / Upheld
            if is_imr:
                content = (
                    f"<b>DECISION: UPHELD — NOT MEDICALLY NECESSARY</b>\n\n"
                    f"Upon independent medical review, the prior utilization review determination is "
                    f"upheld. The requested treatment does not meet criteria for medical necessity "
                    f"based on the submitted evidence and applicable treatment guidelines."
                )
            else:
                content = (
                    f"<b>DECISION: NOT MEDICALLY NECESSARY — DENIED</b>\n\n"
                    f"The requested treatment is not approved at this time. Based on review of the "
                    f"submitted medical records and applicable MTUS guidelines, the treatment does not "
                    f"meet criteria for medical necessity for the documented condition at this stage."
                )
        elements.extend(self.make_section("DECISION", content))
        return elements

    def _build_rationale(self, decision_type, body_parts):
        """Rationale with 6-8 points and MTUS citations."""
        elements = []
        # Map decision type to rationale key
        if "APPROVED" in decision_type and "MODIFICATION" not in decision_type and "OVERTURNED" in decision_type:
            rat_key = "approved"
        elif "APPROVED" in decision_type and "MODIFICATION" not in decision_type:
            rat_key = "approved"
        elif "MODIFICATION" in decision_type:
            rat_key = "modified"
        else:
            rat_key = "denied"

        rationale = get_clinical_rationale(rat_key, body_parts, count=random.randint(5, 7))
        citations = get_mtus_citations(body_parts, count=3)
        citations_text = "\n".join([f"• {c}" for c in citations])

        content = (
            f"{rationale}\n\n"
            f"<b>Supporting Guidelines:</b>\n{citations_text}"
        )
        elements.extend(self.make_section("RATIONALE", content))
        return elements

    def _build_imr_evidence(self):
        """IMR-specific evidence review section."""
        elements = []
        content = (
            "The following evidence was considered in this independent medical review:\n\n"
            "• Medical records submitted by the requesting physician\n"
            "• Prior utilization review determination and rationale\n"
            "• MTUS/ACOEM treatment guidelines for the documented condition\n"
            "• Peer-reviewed medical literature relevant to the requested treatment\n"
            "• Patient's treatment history and clinical course\n\n"
            f"The reviewer's credentials include board certification in the relevant specialty "
            f"with {random.randint(10, 25)} years of clinical experience."
        )
        elements.extend(self.make_section("EVIDENCE REVIEWED", content))
        return elements

    def _build_appeal_rights(self):
        """Appeal rights notice."""
        elements = []
        content = (
            "<b>IMPORTANT NOTICE OF APPEAL RIGHTS</b>\n\n"
            "If you disagree with this decision, you have the right to request an Independent "
            "Medical Review (IMR). You must submit your request within six (6) months of receipt "
            "of this decision. Your request must be submitted in writing to the Administrative "
            "Director, Division of Workers' Compensation.\n\n"
            "For IMR requests:\n"
            "• Phone: (800) 794-6900\n"
            "• DWC IMR Application Form\n\n"
            "This decision does not affect your right to file for dispute resolution through "
            "the Workers' Compensation Appeals Board."
        )
        elements.extend(self.make_section("APPEAL RIGHTS", content))
        return elements

    def _build_reviewer_signature(self, is_imr):
        """Reviewer signature with credentials."""
        elements = []
        first = random.choice(["Patricia", "Richard", "Elizabeth", "William", "Jennifer", "James"])
        last = random.choice(["Thompson", "Garcia", "Wilson", "Davis", "Martinez", "Anderson"])
        reviewer_name = f"Dr. {first} {last}"

        specialty = random.choice([
            "Internal Medicine", "Orthopedic Surgery", "Pain Management",
            "Physical Medicine & Rehabilitation", "Neurology",
        ])
        years = random.randint(10, 30)

        elements.append(Spacer(1, 0.4 * inch))
        if is_imr:
            title = "Independent Medical Reviewer"
        else:
            title = "Medical Director, Utilization Review"

        elements.extend(self.make_signature_block(
            reviewer_name, title, f"CA License #{random.randint(10000, 99999)}",
        ))
        elements.append(Paragraph(
            f"<i>Board Certified in {specialty} — {years} years clinical experience</i>",
            self.styles["SmallItalic"],
        ))
        elements.append(Spacer(1, 0.1 * inch))
        elements.append(Paragraph(
            f"<i>UR Decision Reference: {'IMR' if is_imr else 'UR'}{random.randint(100000, 999999)}</i>",
            self.styles["SmallItalic"],
        ))

        return elements
