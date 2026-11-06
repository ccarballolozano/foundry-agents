from typing import Annotated

from agent_framework import tool
from agent_framework.observability import get_tracer
from pydantic import Field


_BENEFITS = {
    "health insurance": {
        "name": "Health Insurance",
        "description": "Medical, dental and vision coverage for employees and eligible dependents.",
        "eligibility": "Employees working at least 20 hours per week.",
    },
    "remote work": {
        "name": "Remote Work",
        "description": "Employees can work remotely according to the company's hybrid work policy.",
        "eligibility": "Available to eligible employees after completing onboarding.",
    },
    "learning budget": {
        "name": "Learning Budget",
        "description": "Annual budget for courses, conferences, books and other professional development activities.",
        "eligibility": "All full-time employees.",
    },
}


tracer = get_tracer()


@tool
def get_benefit_details(
    benefit_name: Annotated[
        str,
        Field(description="The name of the employee benefit to look up."),
    ],
) -> str:
    """Get details about an employee benefit."""

    with tracer.start_as_current_span("benefit.lookup") as span:
        span.set_attribute("benefit.name", benefit_name)

        benefit = _BENEFITS.get(benefit_name.lower())

        if benefit is None:
            available = ", ".join(item["name"] for item in _BENEFITS.values())
            return (
                f"I couldn't find the benefit '{benefit_name}'. "
                f"Available benefits are: {available}."
            )

        return (
            f"Benefit: {benefit['name']}\n"
            f"Description: {benefit['description']}\n"
            f"Eligibility: {benefit['eligibility']}"
        )
