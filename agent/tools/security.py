import urllib.request
import json
from dataclasses import dataclass, field
from typing import List

@dataclass
class Vulnerability:
    id: str
    summary: str
    fixed_versions: List[str] = field(default_factory=list)

@dataclass
class SecurityAssessment:
    status: str  # "VULNERABLE", "SAFE", "UNKNOWN"
    vulnerabilities: List[Vulnerability] = field(default_factory=list)
    fixed_versions: List[str] = field(default_factory=list)
    reason: str = ""

def assess_security(package_name: str, version: str) -> SecurityAssessment:
    url = "https://api.osv.dev/v1/query"
    payload = {
        "package": {
            "name": package_name,
            "ecosystem": "PyPI"
        },
        "version": version
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return SecurityAssessment(status="UNKNOWN", reason=f"HTTP {resp.status}")
            response_data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return SecurityAssessment(status="UNKNOWN", reason=f"Network or parse error: {str(e)}")
        
    vulns = response_data.get("vulns", [])
    
    if not vulns:
        return SecurityAssessment(status="SAFE", reason="No vulnerabilities reported by OSV for this version")
        
    vulnerabilities = []
    all_fixed_versions = set()
    
    for v in vulns:
        vid = v.get("id", "UNKNOWN-ID")
        summary = v.get("summary", "")
        
        fixed_for_this_vuln = []
        for affected in v.get("affected", []):
            if affected.get("package", {}).get("name") == package_name:
                for r in affected.get("ranges", []):
                    if r.get("type") == "ECOSYSTEM":
                        for event in r.get("events", []):
                            if "fixed" in event:
                                fixed_for_this_vuln.append(event["fixed"])
                                all_fixed_versions.add(event["fixed"])
        
        vulnerabilities.append(Vulnerability(id=vid, summary=summary, fixed_versions=fixed_for_this_vuln))
        
    return SecurityAssessment(
        status="VULNERABLE", 
        vulnerabilities=vulnerabilities, 
        fixed_versions=sorted(list(all_fixed_versions)),
        reason=f"Found {len(vulnerabilities)} vulnerabilities"
    )
