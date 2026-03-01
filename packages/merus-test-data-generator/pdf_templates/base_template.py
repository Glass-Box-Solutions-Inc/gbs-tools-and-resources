"""
Base PDF template — letterheads, headers, signatures, footers, lorem generators.
All specialized templates inherit from this.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


class BaseTemplate:
    """Base class for all PDF templates."""

    def __init__(self, case: Any):
        self.case = case
        self.styles = getSampleStyleSheet()
        self._register_custom_styles()

    def _register_custom_styles(self) -> None:
        self.styles.add(ParagraphStyle(
            name="Letterhead",
            fontSize=14,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
            spaceAfter=2,
        ))
        self.styles.add(ParagraphStyle(
            name="LetterheadSub",
            fontSize=9,
            fontName="Helvetica",
            alignment=TA_CENTER,
            spaceAfter=1,
            textColor=colors.HexColor("#555555"),
        ))
        self.styles.add(ParagraphStyle(
            name="SectionHeader",
            fontSize=11,
            fontName="Helvetica-Bold",
            spaceAfter=6,
            spaceBefore=12,
        ))
        self.styles.add(ParagraphStyle(
            name="BodyText14",
            fontSize=10,
            fontName="Times-Roman",
            leading=14,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        ))
        self.styles.add(ParagraphStyle(
            name="DoubleSpaced",
            fontSize=12,
            fontName="Times-Roman",
            leading=24,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        ))
        self.styles.add(ParagraphStyle(
            name="MonoFindings",
            fontSize=9,
            fontName="Courier",
            leading=12,
            spaceAfter=4,
        ))
        self.styles.add(ParagraphStyle(
            name="SmallItalic",
            fontSize=8,
            fontName="Helvetica-Oblique",
            textColor=colors.HexColor("#888888"),
        ))
        self.styles.add(ParagraphStyle(
            name="RightAligned",
            fontSize=10,
            fontName="Times-Roman",
            alignment=TA_RIGHT,
        ))
        self.styles.add(ParagraphStyle(
            name="CenterBold",
            fontSize=11,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
            spaceAfter=6,
        ))
        self.styles.add(ParagraphStyle(
            name="TableCell",
            fontSize=9,
            fontName="Helvetica",
            leading=11,
        ))
        self.styles.add(ParagraphStyle(
            name="Transcript",
            fontSize=10,
            fontName="Courier",
            leading=14,
            leftIndent=36,
        ))

    def generate(self, output_path: Path, doc_spec: Any) -> Path:
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )
        story = self.build_story(doc_spec)
        doc.build(story, onFirstPage=self._add_footer, onLaterPages=self._add_footer)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(buffer.getvalue())
        return output_path

    def build_story(self, doc_spec: Any) -> list:
        raise NotImplementedError

    # --- Reusable components ---

    def make_letterhead(self, org: str, address: str, phone: str) -> list:
        return [
            Paragraph(org, self.styles["Letterhead"]),
            Paragraph(address, self.styles["LetterheadSub"]),
            Paragraph(phone, self.styles["LetterheadSub"]),
            HRFlowable(width="100%", thickness=1, color=colors.HexColor("#333333")),
            Spacer(1, 12),
        ]

    def make_patient_header(self) -> list:
        a = self.case.applicant
        data = [
            ["Patient:", a.full_name, "DOB:", a.date_of_birth.strftime("%m/%d/%Y")],
            ["SSN (last 4):", f"XXX-XX-{a.ssn_last_four}", "Phone:", a.phone],
        ]
        t = Table(data, colWidths=[80, 200, 60, 140])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
        ]))
        return [t, Spacer(1, 6)]

    def make_claim_reference_block(self) -> list:
        inj = self.case.injuries[0]
        ins = self.case.insurance
        emp = self.case.employer
        data = [
            ["ADJ Number:", inj.adj_number, "Claim #:", ins.claim_number],
            ["Date of Injury:", inj.date_of_injury.strftime("%m/%d/%Y"), "Employer:", emp.company_name],
            ["Injury Type:", inj.injury_type.value.replace("_", " ").title(), "Carrier:", ins.carrier_name],
            ["Body Parts:", ", ".join(inj.body_parts), "", ""],
        ]
        t = Table(data, colWidths=[85, 175, 65, 155])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f0f0")),
            ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f0f0f0")),
        ]))
        return [t, Spacer(1, 12)]

    def make_signature_block(self, name: str, title: str, license_num: str = "") -> list:
        elements = [
            Spacer(1, 30),
            HRFlowable(width="40%", thickness=0.5, color=colors.black),
            Paragraph(name, self.styles["BodyText14"]),
            Paragraph(title, self.styles["SmallItalic"]),
        ]
        if license_num:
            elements.append(Paragraph(f"License: {license_num}", self.styles["SmallItalic"]))
        return elements

    def make_date_line(self, label: str, d: date) -> Paragraph:
        return Paragraph(f"<b>{label}:</b> {d.strftime('%B %d, %Y')}", self.styles["BodyText14"])

    def make_section(self, title: str, content: str) -> list:
        return [
            Paragraph(title, self.styles["SectionHeader"]),
            Paragraph(content, self.styles["BodyText14"]),
        ]

    def make_hr(self) -> HRFlowable:
        return HRFlowable(width="100%", thickness=0.5, color=colors.grey)

    def _add_footer(self, canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#999999"))
        canvas.drawString(
            0.75 * inch, 0.4 * inch,
            "CONFIDENTIAL — Workers' Compensation Medical/Legal Record"
        )
        canvas.drawRightString(
            letter[0] - 0.75 * inch, 0.4 * inch,
            f"Page {doc.page}"
        )
        canvas.restoreState()

    # --- Lorem generators ---

    @staticmethod
    def lorem_medical(sentences: int = 3) -> str:
        pool = [
            "Patient presents with complaints of persistent pain and limited range of motion.",
            "Physical examination reveals tenderness to palpation over the affected area with guarding.",
            "Neurological examination demonstrates intact sensation and motor function bilaterally.",
            "Range of motion is restricted in flexion and extension compared to contralateral side.",
            "No signs of acute distress; patient is alert and oriented x3.",
            "Muscle strength testing reveals 4/5 weakness in the affected extremity.",
            "Deep tendon reflexes are 2+ and symmetric bilaterally.",
            "Straight leg raise test is positive on the affected side at 45 degrees.",
            "Spurling's test reproduces radicular symptoms with lateral flexion.",
            "Gait is antalgic with reduced stride length on the affected side.",
            "Imaging studies correlate with clinical findings of degenerative changes.",
            "Patient reports pain level of 6/10 at rest, increasing to 8/10 with activity.",
            "Swelling and ecchymosis are noted over the affected joint.",
            "Crepitus is palpable with active range of motion testing.",
            "Provocative testing reproduces the patient's primary complaint.",
            "Sensory examination reveals diminished light touch in the affected dermatome.",
            "Patient demonstrates functional limitations consistent with objective findings.",
            "No evidence of malingering or symptom magnification on Waddell's testing.",
        ]
        return " ".join(random.sample(pool, min(sentences, len(pool))))

    @staticmethod
    def lorem_legal(sentences: int = 3) -> str:
        pool = [
            "Applicant sustained industrial injury arising out of and in the course of employment.",
            "The injury is compensable under Labor Code sections 3600 et seq.",
            "Defendant carrier has accepted liability for the claimed body parts.",
            "Medical treatment has been provided pursuant to Labor Code section 4600.",
            "Temporary disability benefits have been paid at the statutory rate.",
            "The matter is now at issue regarding permanent disability and need for future medical treatment.",
            "Applicant's treating physician has indicated that the condition is permanent and stationary.",
            "A Qualified Medical Evaluator has been appointed to address disputed medical issues.",
            "Discovery is ongoing to determine the extent of permanent disability.",
            "The parties have been unable to resolve the matter informally.",
            "Applicant reserves the right to claim additional body parts as supported by medical evidence.",
            "The employer had knowledge of the injury and timely reported same to the carrier.",
            "All statutory notices have been provided to the applicant as required by law.",
            "The matter is set for hearing before the Workers' Compensation Appeals Board.",
        ]
        return " ".join(random.sample(pool, min(sentences, len(pool))))

    @staticmethod
    def lorem_correspondence(sentences: int = 3) -> str:
        pool = [
            "Please find enclosed the documents referenced in our prior correspondence.",
            "We are writing to advise you of the current status of this workers' compensation claim.",
            "Kindly review the attached and respond at your earliest convenience.",
            "This letter serves as formal notice regarding the above-referenced matter.",
            "We have completed our review of the medical records and provide the following summary.",
            "Please do not hesitate to contact our office should you require additional information.",
            "We look forward to resolving this matter in an expeditious manner.",
            "Enclosed please find copies of all relevant documentation for your records.",
            "Thank you for your prompt attention to this matter.",
            "We respectfully request a response within thirty (30) days of the date of this letter.",
        ]
        return " ".join(random.sample(pool, min(sentences, len(pool))))
