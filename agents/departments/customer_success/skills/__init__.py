"""
customer_success/skills/__init__.py
Department-specific skill executors for the CUSTOMER_SUCCESS department.

Skills are triggered by config.yaml trigger_phrases.
Add skill logic here as Python classes.

Pattern:
    customer_success_<skill_id>.py  ->  class <SkillName>Skill
        skill_id = "<skill_id>"
        async def run(self, query, user_permissions) -> SkillResult: ...
"""
