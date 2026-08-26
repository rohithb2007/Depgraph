from dataclasses import dataclass, field
from typing import List, Optional
from packaging.version import Version, InvalidVersion
from packaging.specifiers import SpecifierSet

TARGET_PYTHON = Version("3.11")

@dataclass
class RiskAssessment:
    score: int
    level: str
    reasons: List[str] = field(default_factory=list)

def assess_risk(
    old_version_str: str,
    new_version_str: str,
    requires_python: Optional[str] = None,
    install_success: Optional[bool] = None,
    test_success: Optional[bool] = None,
    current_security_status: str = "UNKNOWN",
    candidate_security_status: str = "UNKNOWN",
    impact_files: int = 0
) -> RiskAssessment:
    """
    Calculates a deterministic explainable risk score (0-100) for a dependency upgrade.
    """
    score = 0
    reasons = []

    # 1. Version Jump
    try:
        old_v = Version(old_version_str)
        new_v = Version(new_version_str)
        
        if new_v.major > old_v.major:
            score += 40
            reasons.append("major version change")
        elif new_v.minor > old_v.minor:
            score += 20
            reasons.append("minor version change")
        elif new_v.micro > old_v.micro:
            score += 5
            reasons.append("patch version change")
        else:
            # same version or pre-release downgrade etc
            pass
    except InvalidVersion:
        score += 20
        reasons.append("invalid version format, jump unknown")

    # 2. Python Compatibility
    if requires_python:
        try:
            if TARGET_PYTHON not in SpecifierSet(requires_python):
                score += 100
                reasons.append("candidate incompatible with target Python 3.11")
        except Exception:
            score += 20
            reasons.append("invalid requires_python specifier")

    # 3. Installation Result
    if install_success is False:
        score += 50
        reasons.append("installation failed")
    
    # 4. Test Result
    if test_success is False:
        score += 50
        reasons.append("test regression detected")

    # 5. Security Information
    if current_security_status == "VULNERABLE":
        score += 15
        reasons.append("pinned version has known vulnerabilities")
        
    if candidate_security_status == "UNKNOWN":
        score += 10
        reasons.append("candidate security status unknown")
    elif candidate_security_status == "VULNERABLE":
        score += 100
        reasons.append("candidate has known security vulnerabilities")
    
    if current_security_status == "VULNERABLE" and candidate_security_status == "SAFE":
        score -= 15 # Positive security evidence offsets the pinned vulnerability penalty
        reasons.append("candidate resolves pinned vulnerabilities (positive security evidence)")

    # 6. Impact Information
    if impact_files > 0:
        impact_score = min(impact_files * 2, 20)
        score += impact_score
        reasons.append(f"impacts {impact_files} files")

    # Cap score
    score = max(0, min(score, 100))

    # Level mapping
    if score >= 80:
        level = "CRITICAL"
    elif score >= 60:
        level = "HIGH"
    elif score >= 30:
        level = "MEDIUM"
    else:
        level = "LOW"

    return RiskAssessment(score=score, level=level, reasons=reasons)
