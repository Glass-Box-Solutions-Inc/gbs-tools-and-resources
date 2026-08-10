"""
Diagnostic Report Template (MRI/CT/X-ray)

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import random
from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer
from reportlab.lib.units import inch

from data.variant_content import diagnostic_register


class DiagnosticReport(BaseTemplate):
    """Radiology and diagnostic imaging report.

    Four registry subtypes route here — imaging, lab results, EMG/NCV and sleep
    study — and until the variant-content seam all four rendered the same
    MRI/CT/X-ray report. With ``variant_content`` set, the three that are not
    radiology render their own document; the imaging variant and every
    unrecognised variant keep rendering the report below, byte for byte.
    """

    def build_story(self, doc_spec):
        """Dispatch to a variant register when one is opted into and claims it."""
        if self.variant_content_enabled(doc_spec):
            register = diagnostic_register(self.variant_of(doc_spec))
            if register is not None:
                return self._build_register_story(doc_spec, register)
        return self._build_imaging_story(doc_spec)

    def _build_imaging_story(self, doc_spec):
        """Build 1-2 page diagnostic imaging report"""
        story = []
        injury = self.case.injuries[0] if self.case.injuries else None
        body_part = ", ".join(injury.body_parts) if injury else "Spine"

        # Imaging center letterhead
        facility_name = random.choice([
            "Pacific Radiology Associates",
            "California Diagnostic Imaging",
            "Advanced MRI & CT Center",
            "Coastal Imaging Center"
        ])
        story.extend(self.make_letterhead(
            facility_name,
            f"{random.randint(100, 9999)} Medical Center Drive\nSuite {random.randint(100, 500)}\n"
            f"San Francisco, CA 9411{random.randint(0, 9)}",
            f"({random.randint(400, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"
        ))
        story.append(Spacer(1, 0.3*inch))

        # Patient header
        story.extend(self.make_patient_header())
        story.append(Spacer(1, 0.3*inch))

        # Exam details
        exam_type = random.choice(["MRI", "CT", "X-Ray"])
        story.append(Paragraph(f"<b>EXAMINATION:</b> {exam_type} {body_part}", self.styles['BodyText14']))
        story.append(Paragraph(f"<b>Date of Exam:</b> {doc_spec.doc_date.strftime('%B %d, %Y')}", self.styles['BodyText14']))
        story.append(Paragraph(f"<b>Ordering Physician:</b> {self.case.treating_physician.full_name}", self.styles['BodyText14']))
        story.append(Spacer(1, 0.2*inch))

        # Clinical indication
        indication = (
            f"Patient presents with work-related {injury.injury_type.value.replace('_', ' ') if injury else 'injury'} "
            f"to {body_part.lower()}. Clinical evaluation for extent of internal derangement and structural abnormalities."
        )
        story.extend(self.make_section("CLINICAL INDICATION", indication))

        # Technique
        if exam_type == "MRI":
            technique = (
                f"MRI of the {body_part.lower()} was performed without contrast using standard sagittal T1, "
                f"T2, and STIR sequences, as well as axial T2 and gradient echo sequences. "
                f"Field strength: {random.choice(['1.5', '3.0'])} Tesla."
            )
        elif exam_type == "CT":
            technique = (
                f"CT of the {body_part.lower()} was performed without contrast in axial plane "
                f"with coronal and sagittal reformations. Slice thickness: {random.choice(['1', '2', '3'])} mm."
            )
        else:
            technique = (
                f"Radiographic examination of the {body_part.lower()} was performed including "
                f"{random.choice(['AP and lateral', 'AP, lateral, and oblique', 'multiple standard views'])} projections."
            )

        story.extend(self.make_section("TECHNIQUE", technique))

        # Findings
        findings_text = self.lorem_medical(random.randint(5, 8))
        story.extend(self.make_section("FINDINGS", findings_text))

        # Impression
        severity = random.choice(["mild", "moderate", "moderate-to-severe"])
        impression_items = []

        if injury and injury.injury_type:
            impression_items.append(f"1. {injury.injury_type.value.replace('_', ' ').title()} of {body_part.lower()} with {severity} findings.")

        impression_items.extend([
            f"2. {random.choice(['Evidence of', 'Findings consistent with', 'Presence of'])} "
            f"{random.choice(['degenerative changes', 'soft tissue edema', 'structural abnormalities'])}.",
            f"3. {random.choice(['Recommend clinical correlation', 'Suggest follow-up imaging if clinically indicated', 'Clinical correlation recommended'])}."
        ])

        impression_content = "\n\n".join(impression_items)
        story.extend(self.make_section("IMPRESSION", impression_content))

        # Radiologist signature
        radiologist_name = f"Dr. {random.choice(['Robert', 'Jennifer', 'Michael', 'Sarah', 'David'])} "
        radiologist_name += random.choice(['Chen', 'Patel', 'Johnson', 'Martinez', 'Lee'])

        story.append(Spacer(1, 0.4*inch))
        story.extend(self.make_signature_block(
            radiologist_name,
            "Board Certified Radiologist",
            f"CA License #{random.randint(10000, 99999)}"
        ))

        return story

    # ------------------------------------------------------------------
    # Variant registers (opt-in only — see BaseTemplate.VARIANT_CONTENT_KEY)
    # ------------------------------------------------------------------

    def _result_row(self, label, value, unit, reference):
        """One reported result line, aligned the way a result table reads."""
        unit_part = f" {unit}" if unit else ""
        return Paragraph(
            f"{label}: <b>{value}</b>{unit_part} &nbsp;&nbsp;(Reference Range: {reference})",
            self.styles['BodyText14'],
        )

    def _build_register_story(self, doc_spec, register):
        """Render a non-radiology diagnostic document.

        Shares the substrate's letterhead, patient header and signature
        scaffolding — a lab report and a radiology report are the same kind of
        artifact administratively. What differs is everything clinical, which is
        what the register supplies.
        """
        story = []
        injury = self.case.injuries[0] if self.case.injuries else None
        body_part = ", ".join(injury.body_parts) if injury else "Spine"

        facility_name = random.choice(register.facilities)
        story.extend(self.make_letterhead(
            facility_name,
            f"{random.randint(100, 9999)} Medical Center Drive\nSuite {random.randint(100, 500)}\n"
            f"San Francisco, CA 9411{random.randint(0, 9)}",
            f"({random.randint(400, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"
        ))
        story.append(Spacer(1, 0.3*inch))

        story.extend(self.make_patient_header())
        story.append(Spacer(1, 0.3*inch))

        story.append(Paragraph(f"<b>EXAMINATION:</b> {register.exam_label}", self.styles['BodyText14']))
        story.append(Paragraph(
            f"<b>Date of Service:</b> {doc_spec.doc_date.strftime('%B %d, %Y')}",
            self.styles['BodyText14'],
        ))
        story.append(Paragraph(
            f"<b>Ordering Physician:</b> {self.case.treating_physician.full_name}",
            self.styles['BodyText14'],
        ))
        story.append(Spacer(1, 0.2*inch))

        indication = (
            f"Evaluation in connection with a work-related "
            f"{injury.injury_type.value.replace('_', ' ') if injury else 'injury'} "
            f"involving the {body_part.lower()}."
        )
        story.extend(self.make_section("CLINICAL INDICATION", indication))

        story.extend(self.make_section("TECHNIQUE", random.choice(register.technique)))

        if register.key == "lab":
            story.extend(self._build_lab_results(register))
        elif register.key == "emg_ncv":
            story.extend(self._build_electrodiagnostic_results(register, body_part))
        else:
            story.extend(self._build_measurement_results(register))

        story.extend(self.make_section("IMPRESSION", random.choice(register.impressions)))

        signer = f"Dr. {random.choice(['Robert', 'Jennifer', 'Michael', 'Sarah', 'David'])} "
        signer += random.choice(['Chen', 'Patel', 'Johnson', 'Martinez', 'Lee'])
        story.append(Spacer(1, 0.4*inch))
        story.extend(self.make_signature_block(
            signer,
            register.signer_title,
            f"{register.signer_credential} #{random.randint(10000, 99999)}",
        ))

        return story

    def _build_lab_results(self, register):
        """A named panel with per-analyte results and reference intervals."""
        from data.variant_content import LAB_PANELS

        panel_name = random.choice(sorted(LAB_PANELS))
        rows = [Paragraph(f"<b>{register.result_heading} — {panel_name}</b>", self.styles['BodyText14'])]
        for analyte in LAB_PANELS[panel_name]:
            rows.append(
                self._result_row(
                    analyte.name, random.choice(analyte.values), analyte.unit, analyte.reference
                )
            )
        rows.append(Spacer(1, 0.2*inch))
        return rows

    def _build_electrodiagnostic_results(self, register, body_part):
        """Nerve conduction rows, then the needle examination."""
        from data.variant_content import EMG_ROWS, NCV_ROWS

        rows = [Paragraph(f"<b>{register.result_heading}</b>", self.styles['BodyText14'])]
        for nerve, latencies, amplitudes, velocities, reference in NCV_ROWS:
            rows.append(Paragraph(
                f"{nerve}: latency <b>{random.choice(latencies)}</b> ms, "
                f"amplitude <b>{random.choice(amplitudes)}</b>, "
                f"conduction velocity <b>{random.choice(velocities)}</b> m/s "
                f"&nbsp;&nbsp;(Reference Range: {reference})",
                self.styles['BodyText14'],
            ))
        rows.append(Spacer(1, 0.2*inch))

        rows.append(Paragraph("<b>NEEDLE EMG</b>", self.styles['BodyText14']))
        for muscle, insertional, spontaneous, muap, recruitment in EMG_ROWS:
            rows.append(Paragraph(
                f"{muscle}: insertional activity {random.choice(insertional).lower()}, "
                f"spontaneous activity {random.choice(spontaneous).lower()}, "
                f"motor unit potentials {random.choice(muap).lower()}, "
                f"recruitment {random.choice(recruitment).lower()}.",
                self.styles['BodyText14'],
            ))
        rows.append(Spacer(1, 0.2*inch))
        return rows

    def _build_measurement_results(self, register):
        """A measurement summary — the shape a sleep study reports in."""
        rows = [Paragraph(f"<b>{register.result_heading}</b>", self.styles['BodyText14'])]
        for analyte in register.analytes:
            rows.append(
                self._result_row(
                    analyte.name, random.choice(analyte.values), analyte.unit, analyte.reference
                )
            )
        rows.append(Spacer(1, 0.2*inch))
        return rows
