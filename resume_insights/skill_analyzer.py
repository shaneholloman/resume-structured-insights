import re
import copy
from typing import Dict, List
from resume_insights.utils import parse_date
from resume_insights.models import SkillDetail

class SkillAnalyzer:
    """
    Class for extracting and analyzing skills from resumes.
    """
    
    def __init__(self, query_engine):
        """
        Initialize the skill analyzer.
        
        Args:
            query_engine: The query engine to use for extracting information
        """
        self.query_engine = query_engine
        
    def extract_skills_with_details(
        self, resume_text: str, work_history: List[Dict]
    ) -> Dict[str, SkillDetail]:
        """
        Extract skills with detailed information including categories, proficiency, and experience.

        Args:
            resume_text: The full text of the resume
            work_history: Parsed work history sections

        Returns:
            Dict[str, SkillDetail]: Dictionary of skills with their details
        """
        # 1. Extract raw skills using LLM
        raw_skills = self._extract_raw_skills()

        # 2. Categorize skills using predefined taxonomies
        categorized_skills = self._categorize_skills(raw_skills)

        # 3. Calculate experience duration by analyzing work history sections
        skills_with_experience = self._calculate_experience_duration(
            categorized_skills, work_history
        )

        # 4. Estimate proficiency based on various factors
        skills_with_proficiency = self._estimate_proficiency(
            skills_with_experience, resume_text
        )

        # 5. Find related skills
        skill_details = self._find_related_skills(skills_with_proficiency)

        return skill_details

    def _extract_raw_skills(self) -> List[str]:
        """
        Extract raw skills from resume text using LLM.

        Returns:
            List[str]: List of raw skills
        """
        prompt = """
        Given the resume text, please identify and list all technical skills, soft skills, and domain knowledge.
        Return only the list of skills without any additional text or explanations.
        """

        response_obj = self.query_engine.query(prompt)
        skills = []

        try:
            # For llama_index.core.base.response.schema.Response objects
            if hasattr(response_obj, "response"):
                skills_text = str(response_obj)

                # If the response is a string
                if isinstance(skills_text, str):
                    # Try to split it into categories if it's a multi-line string
                    categories = [
                        s.strip() for s in skills_text.split("\n") if s.strip()
                    ]
                    for category in categories:
                        # Check if the category follows the format "Category: skill1, skill2, ..."
                        if ": " in category:
                            parts = category.split(": ", 1)
                            if len(parts) == 2:
                                # Extract the skills part and split by commas
                                skills_part = parts[1]
                                category_skills = [
                                    s.strip().lstrip("-*•").strip()
                                    for s in skills_part.split(", ")
                                ]
                                skills.extend(category_skills)
                        else:
                            # If the category doesn't follow the expected format, treat the whole line as a skill
                            skills.append(category.strip().lstrip("-*•").strip())
            else:
                print(
                    f"Response object doesn't have a 'response' attribute: {type(response_obj)}"
                )

        except Exception as e:
            print(f"Error processing skills: {e}")

        return skills

    def _categorize_skills(self, skills: List[str]) -> Dict[str, List[str]]:
        """
        Args:
        skills: List of raw skills

        Returns:
            Dict[str, Dict]: Dictionary of categorized skills
        """

        categorized_skills = {}

        prompt = f"""
        For each of the following skills, categorize it into one of these categories:
        - Programming Languages
        - Frameworks & Libraries
        - Tools & Technologies
        - Soft Skills
        - Domain Knowledge
        - Other

        Skills: {', '.join(skills)}

        For each skill, provide the category and any subcategory if applicable.
        """

        response = self.query_engine.query(prompt)
        # Parse the response to get categorized skills
        # If the response is a llama_index.core.base.response.schema.Response object:
        if hasattr(response, "response"):
            skills_text = str(response)
            # Split the text into lines and remove empty lines
            lines = [line.strip() for line in skills_text.split("\n") if line.strip()]

            # Initialize the result dictionary
            categorized_skills = {}
            current_category = None

            for line in lines:
                # Check for category headers (bold text)
                if line.startswith("**") and line.endswith(":**"):
                    # Remove the ** and : from the category name
                    current_category = line.strip("*:")
                    categorized_skills[current_category] = []

                # Check for skills (marked with *)
                elif line.startswith("* ") and current_category:
                    # Remove the * and leading/trailing whitespace
                    skill = line.lstrip("* ").strip()
                    categorized_skills[current_category].append(skill)

        return categorized_skills

    def _calculate_experience_duration(
        self, categorized_skills: Dict[str, List[str]], work_history: List[Dict]
    ) -> Dict[str, List[Dict]]:
        """
        Calculate experience duration for each skill by analyzing work history.

        Args:
            categorized_skills: Dictionary of categorized skills
            work_history: List of work history entries with dates and descriptions

        Returns:
            Dict[str, Dict]: Skills with experience duration added
        """
        skills_with_experience = {}

        # Flatten the skills dictionary
        all_skills = []
        for category, skills in categorized_skills.items():
            all_skills.extend(skills)

        # For each skill, analyze work history to find mentions and calculate duration
        for category, skills in categorized_skills.items():
            skills_with_experience[category] = []

            for skill_name in skills:
                total_experience = 0.0
                mentions = []

                for job in work_history:
                    job_description = job.get("Job description", "")
                    job_title = job.get("Job title", "")
                    company = job.get("Company name", "")

                    # Check if skill is mentioned in job description or title
                    # Use more flexible matching to catch variations and related terms
                    skill_pattern = re.compile(
                        r"\b" + re.escape(skill_name).replace(r"\ ", r"\s*"),
                        re.IGNORECASE,
                    )

                    if skill_pattern.search(job_description) or skill_pattern.search(
                        job_title
                    ):
                        # Calculate duration for this job
                        start_date = parse_date(job.get("Start date", ""))
                        end_date = parse_date(
                            job.get("End date", "") or "present"
                        )

                        if start_date and end_date:
                            # Calculate years between dates
                            duration = (end_date - start_date).days / 365.25
                            total_experience += duration

                            # Add to mentions
                            mention = f"{job_title} at {company} ({job.get('Start date', '')} to {job.get('End date', 'present')})"
                            mentions.append(mention)

                # Create skill entry
                skill_entry = {
                    "skill_name": skill_name,
                    "years_experience": (
                        round(total_experience, 1) if total_experience > 0 else None
                    ),
                    "mentions": mentions if mentions else None,
                }

                skills_with_experience[category].append(skill_entry)

        return skills_with_experience

    def _estimate_proficiency(
        self, skills_with_experience: Dict[str, List[Dict]], resume_text: str
    ) -> Dict[str, List[Dict]]:
        """
        Estimate proficiency based on experience duration, frequency of mentions, and context.

        Args:
            skills_with_experience: Skills grouped by category, each with experience data
            resume_text: The full text of the resume

        Returns:
            Dict[str, List[Dict]]: Skills with proficiency estimates added
        """
        skills_with_proficiency = copy.deepcopy(skills_with_experience)

        # Iterate through each category
        for category, skills_list in skills_with_experience.items():
            # Iterate through each skill in the category
            for i, skill_info in enumerate(skills_list):
                skill_name = skill_info.get("skill_name", "")
                years_exp = skill_info.get("years_experience", 0) or 0

                # Calculate base proficiency (0-100 scale)
                # Using a logarithmic scale: 0 years = 0, 1 year = 40, 2 years = 60, 5 years = 80, 10+ years = 95
                if years_exp <= 0:
                    base_proficiency = 0
                elif years_exp < 1:
                    base_proficiency = 30 * years_exp
                elif years_exp < 2:
                    base_proficiency = 30 + (years_exp - 1) * 30
                elif years_exp < 5:
                    base_proficiency = 60 + (years_exp - 2) * 6.67
                elif years_exp < 10:
                    base_proficiency = 80 + (years_exp - 5) * 3
                else:
                    base_proficiency = 95

                # Adjust based on frequency of mentions
                mentions = skill_info.get("mentions", []) or []
                mentions_count = len(mentions)
                mention_bonus = (
                    min(5, mentions_count) * 1
                )  # Up to 5% bonus for multiple mentions

                # Check for proficiency indicators in text
                proficiency_indicators = {
                    "expert": 10,
                    "advanced": 7,
                    "proficient": 5,
                    "intermediate": 0,
                    "familiar": -5,
                    "basic": -10,
                    "beginner": -15,
                }

                # Search for proficiency indicators near skill mentions
                context_adjustment = 0
                for indicator, adjustment in proficiency_indicators.items():
                    # Look for indicator within 50 characters of skill mention
                    pattern = (
                        r"\b"
                        + re.escape(indicator)
                        + r"\b.{0,50}\b"
                        + re.escape(skill_name)
                        + r"\b|\b"
                        + re.escape(skill_name)
                        + r"\b.{0,50}\b"
                        + re.escape(indicator)
                        + r"\b"
                    )
                    if re.search(pattern, resume_text, re.IGNORECASE):
                        context_adjustment = adjustment
                        break

                # Calculate final proficiency
                proficiency = base_proficiency + mention_bonus + context_adjustment
                proficiency = max(0, min(100, proficiency))  # Ensure it's between 0-100

                # Update skill info with proficiency in the copied structure
                skills_with_proficiency[category][i]["proficiency"] = round(
                    proficiency, 1
                )

        return skills_with_proficiency

    def _find_related_skills(
        self, skills_with_proficiency: Dict[str, List[Dict]]
    ) -> Dict[str, SkillDetail]:
        """
        Find related skills for each skill and convert to SkillDetail objects.

        Args:
            skills_with_proficiency: Skills with proficiency estimates organized by category
                Format: {'Category': [{'skill_name': 'Skill', ...}, ...], ...}

        Returns:
            Dict[str, SkillDetail]: Dictionary of SkillDetail objects
        """
        # Extract all skill names first
        all_skills = {}
        for category, skills in skills_with_proficiency.items():
            for skill_info in skills:
                skill_name = skill_info["skill_name"]
                # Store the skill with its category and existing data
                all_skills[skill_name] = {
                    "skill_name": skill_name,
                    "category": category,
                    "proficiency": skill_info.get("proficiency"),
                    "years_experience": skill_info.get("years_experience"),
                    "mentions": skill_info.get("mentions"),
                }

        skill_names = list(all_skills.keys())

        # Process skills in chunks to avoid API limitations
        skill_chunks = [skill_names[i : i + 5] for i in range(0, len(skill_names), 5)]

        for chunk in skill_chunks:
            prompt = f"""
            For each of the following skills, list 2-3 closely related skills from this list: {', '.join(skill_names)}
            Skills to analyze: {', '.join(chunk)}
            
            For each skill, provide only the related skills, separated by commas.
            """

            response = self.query_engine.query(prompt)
            # Parse the response to get related skills
            lines = str(response).split("\n")
            for line in lines:
                if ":" in line:
                    skill, related = line.split(":", 1)
                    skill = skill.strip()
                    if skill in chunk:
                        related_skills = [
                            s.strip()
                            for s in related.split(",")
                            if s.strip() in skill_names and s.strip() != skill
                        ]
                        all_skills[skill]["related_skills"] = (
                            related_skills if related_skills else None
                        )

        # Convert to SkillDetail objects
        skill_details = {}
        for skill_name, skill_info in all_skills.items():
            skill_details[skill_name] = SkillDetail(
                skill_name=skill_info["skill_name"],
                category=skill_info.get("category"),
                proficiency=skill_info.get("proficiency"),
                years_experience=skill_info.get("years_experience"),
                mentions=skill_info.get("mentions"),
                related_skills=skill_info.get("related_skills"),
            )

        return skill_details