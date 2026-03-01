"""
Job Description Template

Generates job descriptions with physical requirements for injured worker positions.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, ListFlowable, ListItem
from reportlab.lib import colors
from reportlab.lib.units import inch
import random
from datetime import timedelta


class JobDescription(BaseTemplate):
    """Job description with physical requirements and essential functions."""

    def build_story(self, doc_spec):
        """Build the job description document."""
        story = []

        # Employer letterhead
        story.extend(
            self.make_letterhead(
                self.case.employer.company_name,
                f"{self.case.employer.address_street}, {self.case.employer.address_city}, CA {self.case.employer.address_zip}",
                self.case.employer.phone,
            )
        )
        story.append(Spacer(1, 0.3 * inch))

        # Title
        story.append(Paragraph("JOB DESCRIPTION", self.styles["CenterBold"]))
        story.append(Spacer(1, 0.2 * inch))

        # Position details table
        supervisor_names = [
            "David Martinez",
            "Linda Chen",
            "James Wilson",
            "Maria Rodriguez",
            "Thomas Anderson",
        ]
        supervisor = random.choice(supervisor_names)

        position_data = [
            ["Position Title:", self.case.employer.position],
            ["Department:", self.case.employer.department or "Operations"],
            ["FLSA Status:", "Non-Exempt"],
            ["Reports To:", supervisor],
            [
                "Effective Date:",
                (self.case.employer.hire_date - timedelta(days=random.randint(30, 180))).strftime("%m/%d/%Y"),
            ],
        ]
        position_table = Table(position_data, colWidths=[2 * inch, 4 * inch])
        position_table.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 10),
                    ("FONT", (1, 0), (1, -1), "Helvetica", 10),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(position_table)
        story.append(Spacer(1, 0.2 * inch))

        # Job summary based on position type
        summaries = {
            "warehouse": f"The {self.case.employer.position} is responsible for receiving, storing, and distributing materials, "
            "equipment, and products within the warehouse facility. This position requires physical stamina and the ability to "
            "operate material handling equipment safely and efficiently. The role involves maintaining accurate inventory records "
            "and ensuring compliance with safety protocols.",
            "construction": f"The {self.case.employer.position} performs skilled construction work in accordance with project specifications "
            "and safety standards. This position requires the ability to work at heights, operate power tools, and lift heavy materials. "
            "The role involves collaborating with team members to complete projects on schedule while maintaining a safe work environment.",
            "healthcare": f"The {self.case.employer.position} provides direct patient care and support under the supervision of licensed "
            "medical professionals. This position requires the ability to assist with patient mobility, perform routine care tasks, and "
            "maintain accurate documentation. The role involves frequent standing, walking, and patient lifting/transferring activities.",
            "retail": f"The {self.case.employer.position} provides excellent customer service while maintaining store operations and "
            "merchandising standards. This position requires the ability to stand for extended periods, stock shelves, and assist "
            "customers with product selections. The role involves cash handling, inventory management, and maintaining a clean, organized store.",
            "food": f"The {self.case.employer.position} prepares and serves food products in accordance with health and safety standards. "
            "This position requires the ability to stand for extended periods, work in various temperatures, and maintain food safety protocols. "
            "The role involves customer service, food preparation, and maintaining cleanliness in the work area.",
        }

        # Determine job category based on position keywords
        position_lower = self.case.employer.position.lower()
        if any(kw in position_lower for kw in ["warehouse", "forklift", "loader", "picker"]):
            job_category = "warehouse"
        elif any(kw in position_lower for kw in ["construction", "carpenter", "electrician", "laborer"]):
            job_category = "construction"
        elif any(kw in position_lower for kw in ["nurse", "aide", "caregiver", "medical", "healthcare"]):
            job_category = "healthcare"
        elif any(kw in position_lower for kw in ["retail", "cashier", "sales", "stocker"]):
            job_category = "retail"
        elif any(kw in position_lower for kw in ["cook", "chef", "server", "food", "kitchen"]):
            job_category = "food"
        else:
            job_category = random.choice(["warehouse", "retail", "food"])

        story.append(Paragraph("Job Summary", self.styles["SectionHeader"]))
        story.append(Paragraph(summaries[job_category], self.styles["BodyText14"]))
        story.append(Spacer(1, 0.2 * inch))

        # Essential functions based on job category
        functions_by_category = {
            "warehouse": [
                "Load and unload delivery trucks using appropriate equipment",
                "Operate forklifts, pallet jacks, and other material handling equipment",
                "Pick and pack orders according to shipping documents",
                "Maintain accurate inventory counts and records in warehouse management system",
                "Stack and organize materials in designated storage areas",
                "Inspect incoming and outgoing shipments for damage or discrepancies",
                "Follow all safety protocols and wear required personal protective equipment",
                "Maintain clean and organized work areas",
            ],
            "construction": [
                "Read and interpret blueprints, drawings, and specifications",
                "Operate power tools, hand tools, and construction equipment safely",
                "Measure, cut, and install materials according to project requirements",
                "Collaborate with team members to complete assigned tasks",
                "Maintain tools and equipment in proper working condition",
                "Follow all safety regulations including fall protection and PPE requirements",
                "Load and unload materials from trucks and transport to work areas",
                "Document work completed and report any issues to supervisor",
            ],
            "healthcare": [
                "Assist patients with activities of daily living including bathing, dressing, and eating",
                "Monitor and document patient vital signs and conditions",
                "Transfer and reposition patients using proper body mechanics and equipment",
                "Maintain patient rooms in clean and sanitary condition",
                "Respond to patient call lights and requests promptly",
                "Follow infection control protocols and standard precautions",
                "Communicate patient status and concerns to nursing staff",
                "Document care provided in electronic medical record system",
            ],
            "retail": [
                "Provide friendly and knowledgeable customer service to all shoppers",
                "Operate cash register and process transactions accurately",
                "Stock shelves and merchandise displays according to planograms",
                "Receive and process incoming shipments",
                "Maintain store cleanliness and organization throughout shift",
                "Answer customer questions about products and services",
                "Monitor inventory levels and report low stock items",
                "Follow loss prevention procedures and report suspicious activity",
            ],
            "food": [
                "Prepare food items according to recipes and safety standards",
                "Maintain cleanliness of food preparation and service areas",
                "Operate kitchen equipment including ovens, grills, and fryers safely",
                "Take customer orders and provide excellent service",
                "Stock food and supply items throughout shift",
                "Follow food safety and sanitation guidelines",
                "Monitor food temperatures and quality",
                "Work collaboratively with team members during busy periods",
            ],
        }

        story.append(Paragraph("Essential Functions", self.styles["SectionHeader"]))
        functions = random.sample(functions_by_category[job_category], 7)
        for func in functions:
            story.append(Paragraph(f"• {func}", self.styles["BodyText14"]))
            story.append(Spacer(1, 0.05 * inch))
        story.append(Spacer(1, 0.15 * inch))

        # Physical requirements
        lifting_requirements = {
            "warehouse": "50-75 lbs frequently, up to 100 lbs occasionally",
            "construction": "50-100 lbs frequently",
            "healthcare": "25-50 lbs frequently (patient transfers with equipment)",
            "retail": "25-50 lbs frequently",
            "food": "25-40 lbs frequently",
        }

        standing_hours = {
            "warehouse": "6-8 hours per shift",
            "construction": "8-10 hours per shift",
            "healthcare": "6-8 hours per shift",
            "retail": "7-8 hours per shift",
            "food": "6-8 hours per shift",
        }

        story.append(Paragraph("Physical Requirements", self.styles["SectionHeader"]))

        phys_req_text = (
            f"<b>Lifting:</b> Must be able to lift and carry {lifting_requirements[job_category]}.<br/>"
            f"<b>Standing/Walking:</b> {standing_hours[job_category]}.<br/>"
            f"<b>Repetitive Motions:</b> Frequent bending, stooping, reaching, and grasping required.<br/>"
            f"<b>Environmental Conditions:</b> "
        )

        if job_category == "warehouse":
            phys_req_text += "Work in varying temperatures; exposure to noise from equipment."
        elif job_category == "construction":
            phys_req_text += "Outdoor work in all weather conditions; exposure to heights, noise, and dust."
        elif job_category == "healthcare":
            phys_req_text += "Exposure to infectious diseases; work with bodily fluids; may encounter aggressive behavior."
        elif job_category == "retail":
            phys_req_text += "Indoor climate-controlled environment; exposure to customer interactions."
        else:  # food
            phys_req_text += "Work in hot kitchen environment; exposure to temperature extremes (freezers/ovens)."

        story.append(Paragraph(phys_req_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.2 * inch))

        # Qualifications
        story.append(Paragraph("Qualifications", self.styles["SectionHeader"]))
        qual_text = (
            "<b>Education:</b> High school diploma or equivalent preferred.<br/>"
            "<b>Experience:</b> "
        )

        if job_category in ["warehouse", "construction"]:
            qual_text += "1-2 years of relevant experience preferred; willing to train qualified candidates.<br/>"
        elif job_category == "healthcare":
            qual_text += "CNA certification or completion of training program required; 6 months experience preferred.<br/>"
        else:
            qual_text += "Previous customer service experience preferred; on-the-job training provided.<br/>"

        qual_text += "<b>Certifications:</b> "
        if job_category == "warehouse":
            qual_text += "Forklift certification required (training provided)."
        elif job_category == "construction":
            qual_text += "OSHA 10 certification preferred; valid driver's license may be required."
        elif job_category == "healthcare":
            qual_text += "Current CNA certification, CPR/First Aid, TB clearance."
        else:
            qual_text += "Food Handler's Card (if applicable); will obtain within 30 days of hire."

        story.append(Paragraph(qual_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.25 * inch))

        # Disclaimer
        story.append(
            Paragraph(
                "This job description is not exhaustive and may be updated as business needs require. "
                "The employee may be asked to perform other duties as assigned. Employment is at-will and "
                "either party may terminate employment at any time with or without cause.",
                self.styles["SmallItalic"],
            )
        )
        story.append(Spacer(1, 0.25 * inch))

        # HR signature
        hr_names = [
            "Patricia Martinez",
            "Robert Chen",
            "Jennifer Williams",
            "Michael Brown",
            "Sarah Johnson",
        ]
        hr_rep = random.choice(hr_names)

        story.append(self.make_hr())
        story.append(Spacer(1, 0.05 * inch))
        story.append(
            Paragraph(
                f"<b>{hr_rep}</b><br/>Human Resources Manager<br/>{doc_spec.doc_date.strftime('%m/%d/%Y')}",
                self.styles["BodyText14"],
            )
        )

        return story
