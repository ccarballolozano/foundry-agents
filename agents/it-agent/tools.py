"""it-agent's IT catalog and its two read-only lookup tools.

The catalog describes the fictional company MyConcepts. It holds no personal
data and no amounts, allowances or budgets: those are HR topics, answered by
hr-agent from the handbook. Delivery and week-1 steps match the handbook's
onboarding checklist (HR ships the laptop or it waits at the desk; account
activation and MFA happen in week 1).
"""

from langchain_core.tools import tool
from opentelemetry import trace

_EQUIPMENT = {
    "software engineer": {
        "laptop": "MacBook Pro 14-inch (M-series, 32 GB memory) with macOS, enrolled in device management.",
        "peripherals": "USB-C dock, 27-inch 4K monitor, wired keyboard and mouse, noise-cancelling headset.",
        "delivery": "HR sends the laptop to your home address before your first day, or it is ready at your office desk.",
    },
    "consultant": {
        "laptop": "Lightweight 14-inch Windows laptop (16 GB memory) with Windows 11, enrolled in device management.",
        "peripherals": "Travel USB-C adapter, wireless mouse, headset with microphone for customer calls.",
        "delivery": "HR sends the laptop to your home address before your first day, or it is ready at your office desk.",
    },
    "sales": {
        "laptop": "13-inch Windows laptop (16 GB memory) with Windows 11, enrolled in device management.",
        "peripherals": "Wireless headset, wireless mouse, company mobile phone for customer contact.",
        "delivery": "HR sends the laptop to your home address before your first day, or it is ready at your office desk.",
    },
}

# Steps every role starts with in week 1, before the role-specific ones.
_COMMON_STEPS = [
    "Week 1: activate your MyConcepts account with the link in your welcome email.",
    "Week 1: set up multi-factor authentication with the Microsoft Authenticator app.",
]

_ACCESS = {
    "software engineer": {
        "accounts": [
            "MyConcepts account (email, Teams, MyConcepts Learn, MyConcepts People)",
            "GitHub organization membership",
            "Azure DevOps project access for your team",
            "Developer access to the non-production Azure subscriptions",
        ],
        "steps": [
            "Sign in to GitHub with your MyConcepts account (single sign-on) to join the organization.",
            "Ask your manager to add you to your team's group; repository and pipeline access follow from it.",
            "Request non-production Azure access in the IT self-service portal; it is approved by your manager.",
        ],
    },
    "consultant": {
        "accounts": [
            "MyConcepts account (email, Teams, MyConcepts Learn, MyConcepts People)",
            "Time-tracking app for project hours",
            "Shared project workspace in SharePoint",
        ],
        "steps": [
            "Sign in to the time-tracking app with your MyConcepts account; your projects appear once staffed.",
            "Your project lead grants access to each project's SharePoint workspace.",
            "Customer accounts, if a project needs them, are requested by the project lead from the customer.",
        ],
    },
    "sales": {
        "accounts": [
            "MyConcepts account (email, Teams, MyConcepts Learn, MyConcepts People)",
            "CRM access with the sales role",
            "Proposals workspace in SharePoint",
        ],
        "steps": [
            "Sign in to the CRM with your MyConcepts account; your sales manager assigns your accounts.",
            "Set up the company mobile phone with the Company Portal app before using email on it.",
        ],
    },
}

tracer = trace.get_tracer("it-agent")


def _not_found(role: str) -> str:
    known = ", ".join(sorted(_EQUIPMENT))
    return f"The role '{role}' is not in the IT catalog. Known roles are: {known}."


@tool
def get_standard_equipment(role: str) -> str:
    """Get the standard IT equipment (laptop and peripherals) that a MyConcepts role receives, and how it is delivered.

    Args:
        role: The employee's role, for example "software engineer", "consultant" or "sales".
    """
    with tracer.start_as_current_span("it.equipment.lookup") as span:
        span.set_attribute("it.role", role)
        entry = _EQUIPMENT.get(role.strip().lower())
        span.set_attribute("it.found", entry is not None)
        if entry is None:
            return _not_found(role)
        return (
            f"Role: {role.strip().lower()}\n"
            f"Laptop: {entry['laptop']}\n"
            f"Peripherals: {entry['peripherals']}\n"
            f"Delivery: {entry['delivery']}"
        )


@tool
def get_access_setup(role: str) -> str:
    """Get the accounts, applications and access that a MyConcepts role gets, and the steps to set them up.

    Args:
        role: The employee's role, for example "software engineer", "consultant" or "sales".
    """
    with tracer.start_as_current_span("it.access.lookup") as span:
        span.set_attribute("it.role", role)
        entry = _ACCESS.get(role.strip().lower())
        span.set_attribute("it.found", entry is not None)
        if entry is None:
            return _not_found(role)
        accounts = "\n".join(f"- {a}" for a in entry["accounts"])
        steps = "\n".join(f"{i}. {s}" for i, s in enumerate(_COMMON_STEPS + entry["steps"], start=1))
        return f"Role: {role.strip().lower()}\nAccounts and access:\n{accounts}\nSetup steps:\n{steps}"
