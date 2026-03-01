"""
Deposition Transcript template for Workers' Compensation discovery.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer, PageBreak
from reportlab.lib.units import inch
from datetime import timedelta
import random


class DepositionTranscript(BaseTemplate):
    """Generates a deposition transcript in Q&A format."""

    def build_story(self, doc_spec):
        """Build the deposition transcript story."""
        story = []

        # Cover page
        story.append(Spacer(1, 1.5 * inch))
        story.append(Paragraph("DEPOSITION OF", self.styles["CenterBold"]))
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph(self.case.applicant.full_name.upper(), self.styles["CenterBold"]))
        story.append(Spacer(1, 0.5 * inch))

        case_info = f"""
        Case: {self.case.applicant.full_name} v. {self.case.employer.company_name}<br/>
        ADJ No.: {self.case.injuries[0].adj_number}<br/>
        <br/>
        Date: {doc_spec.doc_date.strftime('%B %d, %Y')}<br/>
        Time: 10:00 A.M.<br/>
        Location: {self.case.insurance.defense_firm}
        """
        story.append(Paragraph(case_info, self.styles["CenterBold"]))
        story.append(Spacer(1, 0.5 * inch))

        # Reporter info
        reporter_names = [
            "Jennifer Martinez",
            "Robert Chen",
            "Sarah Williams",
            "Michael Johnson",
            "Lisa Thompson"
        ]
        reporter_name = random.choice(reporter_names)
        reporter_number = random.randint(5000, 15000)

        reporter_info = f"""
        Reported by:<br/>
        {reporter_name}<br/>
        Certified Shorthand Reporter No. {reporter_number}
        """
        story.append(Paragraph(reporter_info, self.styles["CenterBold"]))
        story.append(PageBreak())

        # Certification page
        cert_text = f"""
        <b>CERTIFICATION</b><br/>
        <br/>
        I, {reporter_name}, a Certified Shorthand Reporter for the State of California,
        do hereby certify:<br/>
        <br/>
        That prior to being examined, the witness named in the foregoing deposition was by me
        duly sworn to testify to the truth, the whole truth, and nothing but the truth;<br/>
        <br/>
        That said deposition is a true record of the testimony given by said witness;<br/>
        <br/>
        That I am neither counsel for, nor related to, any party to said action, nor in any way
        interested in the outcome thereof.<br/>
        <br/>
        IN WITNESS WHEREOF, I have hereunto set my hand this {doc_spec.doc_date.strftime('%d day of %B, %Y')}.<br/>
        <br/>
        <br/>
        _______________________________<br/>
        {reporter_name}<br/>
        CSR No. {reporter_number}
        """
        story.append(Paragraph(cert_text, self.styles["BodyText14"]))
        story.append(PageBreak())

        # Appearances
        story.append(Paragraph("<b>APPEARANCES</b>", self.styles["SectionHeader"]))
        story.append(Spacer(1, 0.2 * inch))

        appearances = f"""
        For Defendant:<br/>
        {self.case.insurance.defense_attorney}<br/>
        {self.case.insurance.defense_firm}<br/>
        <br/>
        For Applicant:<br/>
        {self.case.applicant.full_name}<br/>
        Appearing in Pro Per
        """
        story.append(Paragraph(appearances, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.3 * inch))

        # Examination header
        story.append(self.make_hr())
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph(
            f"<b>EXAMINATION BY {self.case.insurance.defense_attorney}</b>",
            self.styles["SectionHeader"]
        ))
        story.append(Spacer(1, 0.2 * inch))

        # Generate Q&A exchanges
        line_num = 1
        exchanges = []

        # Background questions
        exchanges.append((
            f"Q. Good morning. Could you please state your full name for the record?",
            f"A. {self.case.applicant.full_name}."
        ))

        exchanges.append((
            f"Q. And what is your date of birth?",
            f"A. {self.case.applicant.date_of_birth.strftime('%B %d, %Y')}."
        ))

        exchanges.append((
            f"Q. What is your current address?",
            f"A. {self.case.applicant.address_street}, {self.case.applicant.address_city}, California, {self.case.applicant.address_zip}."
        ))

        # Employment questions
        exchanges.append((
            f"Q. When did you begin working for {self.case.employer.company_name}?",
            f"A. I started on {self.case.employer.hire_date.strftime('%B %d, %Y')}."
        ))

        exchanges.append((
            f"Q. What was your position?",
            f"A. I was a {self.case.employer.position}."
        ))

        exchanges.append((
            f"Q. Can you describe your typical job duties?",
            f"A. I would {random.choice(['handle materials', 'operate machinery', 'work at a desk', 'serve customers', 'manage inventory'])} "
            f"and {random.choice(['lift boxes', 'stand for long periods', 'use computers', 'drive vehicles', 'assist coworkers'])}. "
            f"It was pretty physical work."
        ))

        # Injury questions
        injury_parts = ", ".join(self.case.injuries[0].body_parts[:2]) if len(self.case.injuries[0].body_parts) > 1 else self.case.injuries[0].body_parts[0]

        exchanges.append((
            f"Q. Can you describe the incident that occurred on {self.case.injuries[0].date_of_injury.strftime('%B %d, %Y')}?",
            f"A. {self.case.injuries[0].description} I immediately felt pain in my {injury_parts}."
        ))

        exchanges.append((
            f"Q. Did you report the injury to your supervisor?",
            f"A. Yes, I reported it {random.choice(['right away', 'the same day', 'within an hour', 'immediately'])}. "
            f"I told {random.choice(['my supervisor', 'the manager', 'HR'])} what happened."
        ))

        exchanges.append((
            f"Q. What symptoms did you experience immediately after the injury?",
            f"A. I had {random.choice(['sharp', 'severe', 'intense', 'stabbing'])} pain in my {injury_parts}. "
            f"I also had {random.choice(['difficulty moving', 'numbness', 'tingling', 'weakness', 'swelling'])}."
        ))

        # Medical treatment questions
        exchanges.append((
            f"Q. Did you seek medical treatment?",
            f"A. Yes, I saw Dr. {self.case.treating_physician.full_name} at {self.case.treating_physician.facility}."
        ))

        exchanges.append((
            f"Q. What treatment did Dr. {self.case.treating_physician.full_name.split()[-1]} provide?",
            f"A. {random.choice(['Physical therapy', 'Medication', 'Injections', 'Surgery was discussed', 'Conservative treatment'])}. "
            f"I've been going to appointments {random.choice(['weekly', 'twice a week', 'every two weeks', 'monthly'])}."
        ))

        exchanges.append((
            f"Q. Are you currently taking any medications for your injury?",
            f"A. Yes, I take {random.choice(['ibuprofen', 'naproxen', 'prescription pain medication', 'muscle relaxers'])} "
            f"as needed for the pain."
        ))

        exchanges.append((
            f"Q. Have you undergone any surgical procedures?",
            f"A. {random.choice(['No, not yet', 'No, Dr. ' + self.case.treating_physician.full_name.split()[-1] + ' wants to try conservative treatment first', 'Yes, I had surgery', 'It has been recommended but not scheduled yet'])}."
        ))

        # Current condition questions
        exchanges.append((
            f"Q. How would you describe your pain level today?",
            f"A. On a scale of one to ten, it's usually around {random.randint(5, 8)}. "
            f"Some days are better than others."
        ))

        exchanges.append((
            f"Q. What activities are you unable to do because of this injury?",
            f"A. I can't {random.choice(['lift heavy objects', 'stand for long periods', 'sit comfortably', 'reach overhead', 'bend down easily'])}. "
            f"Even {random.choice(['sleeping', 'driving', 'household chores', 'exercising'])} is difficult."
        ))

        exchanges.append((
            f"Q. Has your doctor placed any work restrictions on you?",
            f"A. Yes, I'm restricted to {random.choice(['light duty', 'no lifting over 10 pounds', 'sedentary work', 'modified duty'])}."
        ))

        exchanges.append((
            f"Q. Are you currently working?",
            f"A. {random.choice(['No, I have been off work since the injury', 'Yes, but on modified duty', 'No, I was laid off', 'I tried to return but could not perform my duties'])}."
        ))

        # Prior injuries
        exchanges.append((
            f"Q. Did you have any injuries to your {injury_parts} prior to this incident?",
            f"A. {random.choice(['No, never', 'No, this was the first time', 'I had minor soreness from time to time, but nothing like this', 'No previous injuries'])}."
        ))

        exchanges.append((
            f"Q. Have you ever filed a workers' compensation claim before?",
            f"A. {random.choice(['No, this is my first claim', 'No', 'Never before this incident'])}."
        ))

        # Impact questions
        exchanges.append((
            f"Q. How has this injury affected your daily life?",
            f"A. It's been very difficult. I can't do things I used to do. "
            f"{random.choice(['My family has to help me', 'I need assistance with basic tasks', 'I cannot participate in activities I enjoyed', 'I struggle with everyday activities'])}."
        ))

        exchanges.append((
            f"Q. What is your goal for treatment?",
            f"A. I just want to {random.choice(['get back to work', 'reduce my pain', 'return to my normal activities', 'be able to function without pain'])}. "
            f"I want to get better."
        ))

        # Closing
        exchanges.append((
            f"Q. Is there anything else you think I should know about this injury?",
            f"A. {random.choice(['Just that it has changed my life significantly', 'I wish this had never happened', 'I am doing my best to recover', 'I am following all of my treatment recommendations'])}."
        ))

        # Format Q&A with line numbers
        for q, a in exchanges:
            # Question with line numbers
            q_lines = [f"{line_num:>3}  {q}"]
            line_num += 1
            story.append(Paragraph("<br/>".join(q_lines), self.styles["Transcript"]))
            story.append(Spacer(1, 0.1 * inch))

            # Answer with line numbers
            a_lines = [f"{line_num:>3}  {a}"]
            line_num += 1
            story.append(Paragraph("<br/>".join(a_lines), self.styles["Transcript"]))
            story.append(Spacer(1, 0.15 * inch))

        # End of examination
        story.append(Spacer(1, 0.3 * inch))
        story.append(Paragraph(
            f"{line_num:>3}  (Deposition concluded at 11:{random.randint(15, 45)} A.M.)",
            self.styles["Transcript"]
        ))
        story.append(PageBreak())

        # Final certification
        final_cert = f"""
        <b>CERTIFICATE OF REPORTER</b><br/>
        <br/>
        I, {reporter_name}, Certified Shorthand Reporter, hereby certify that the witness in the
        foregoing deposition was by me duly sworn to testify the truth, the whole truth, and nothing
        but the truth; that said deposition was taken down in shorthand by me at the time and place
        therein stated and was thereafter reduced to typewriting under my direction; that the
        foregoing is a true and correct transcript of my shorthand notes so taken.<br/>
        <br/>
        I further certify that I am not of counsel or attorney for either or any of the parties to
        said deposition nor in any way interested in the outcome of the cause named in said caption.<br/>
        <br/>
        IN WITNESS WHEREOF, I have hereunto set my hand this {doc_spec.doc_date.strftime('%d day of %B, %Y')}.<br/>
        <br/>
        <br/>
        <br/>
        _______________________________<br/>
        {reporter_name}<br/>
        Certified Shorthand Reporter No. {reporter_number}<br/>
        State of California
        """
        story.append(Paragraph(final_cert, self.styles["BodyText14"]))

        return story
