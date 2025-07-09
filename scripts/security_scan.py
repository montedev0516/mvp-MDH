import json
import sys


def run_bandit_scan(directory):
    """Run Bandit security scan on the specified directory."""
    try:
        with open("bandit_report.json", "r") as f:
            data = json.load(f)
            return {
                "metrics": data.get("metrics", {}),
                "results": data.get("results", []),
                "generated_at": data.get("generated_at", ""),
            }
    except FileNotFoundError:
        return {"error": "Bandit report file not found", "results": [], "metrics": {}}
    except json.JSONDecodeError as e:
        return {
            "error": f"Failed to parse Bandit report: {str(e)}",
            "results": [],
            "metrics": {},
        }
    except Exception as e:
        return {
            "error": f"Error reading bandit report: {str(e)}",
            "results": [],
            "metrics": {},
        }


def read_safety_report():
    """Read Safety scan results from the report file."""
    try:
        with open("safety_report.json", "r") as f:
            data = json.load(f)
            return {
                "meta": data.get("meta", {}),
                "affected_packages": data.get("affected_packages", []),
                "vulnerabilities": data.get("vulnerabilities", []),
                "remediations": data.get("remediations", []),
            }
    except FileNotFoundError:
        return {"error": "Safety report file not found"}
    except json.JSONDecodeError as e:
        return {"error": f"Failed to parse Safety report: {str(e)}"}
    except Exception as e:
        return {"error": f"Error reading Safety report: {str(e)}"}


def generate_markdown_report(directory):
    """Generate a markdown security report."""
    report_sections = []
    report_sections.append("# Security Scan Results\n")

    # Run Bandit scan
    report_sections.append("## 🔍 Bandit Security Scan\n")
    bandit_results = run_bandit_scan(directory)

    if "error" in bandit_results:
        report_sections.append(f"⚠️ {bandit_results['error']}\n")
    else:
        issues = bandit_results.get("results", [])
        if not issues:
            report_sections.append("✅ No security issues found in code\n")
        else:
            metrics = bandit_results.get("metrics", {}).get("_totals", {})

            # Summary of findings
            report_sections.append("### Summary\n")
            report_sections.append(f"* Total lines scanned: {metrics.get('loc', 0)}\n")
            report_sections.append(f"* Issues found: {len(issues)}\n")
            report_sections.append(
                f"* High severity issues: {metrics.get('SEVERITY.HIGH', 0)}\n"
            )
            report_sections.append(
                f"* Medium severity issues: {metrics.get('SEVERITY.MEDIUM', 0)}\n"
            )
            report_sections.append(
                f"* Low severity issues: {metrics.get('SEVERITY.LOW', 0)}\n\n"
            )

            # Detailed findings
            report_sections.append("### Detailed Findings\n")
            for issue in issues:
                severity = issue.get("issue_severity", "Unknown")
                emoji = (
                    "🔴"
                    if severity == "HIGH"
                    else "🟡"
                    if severity == "MEDIUM"
                    else "🟢"
                )

                report_sections.append(f"""
                {emoji} **{issue.get('issue_text', 'Unknown issue')}**
                * File: `{issue.get('filename', 'Unknown file')}`
                * Line: {issue.get('line_number', 'Unknown')}
                * Severity: {severity}
                * Confidence: {issue.get('issue_confidence', 'Unknown')}
                * More Info: {issue.get('more_info', 'Not available')}
                * Code:
                    ```python
                    {issue.get('code', 'No code available')}
                    ```
                """)

    # Read Safety results
    safety_results = read_safety_report()
    report_sections.append("\n## 📦 Dependency Security Check\n")

    if "error" in safety_results:
        report_sections.append(f"⚠️ {safety_results['error']}\n")
    else:
        meta = safety_results.get("meta", {})
        affected_packages = safety_results.get("affected_packages", [])
        vulnerabilities = safety_results.get("vulnerabilities", [])
        remediations = safety_results.get("remediations", [])

        # Summary
        report_sections.append("### Summary\n")
        report_sections.append(f"* Scan timestamp: {meta.get('timestamp', 'N/A')}\n")
        report_sections.append(
            f"* Packages scanned: {len(meta.get('scanned_packages', []))}\n"
        )
        report_sections.append(f"* Affected packages: {len(affected_packages)}\n")
        report_sections.append(f"* Vulnerabilities found: {len(vulnerabilities)}\n\n")

        if not vulnerabilities:
            report_sections.append(
                "✅ No known vulnerabilities found in dependencies\n"
            )
        else:
            report_sections.append("### Vulnerabilities\n")
            for vuln in vulnerabilities:
                severity = vuln.get("severity", "").upper()
                emoji = (
                    "🔴"
                    if severity == "HIGH"
                    else "🟡"
                    if severity == "MEDIUM"
                    else "🟢"
                )

                report_sections.append(f"""
{emoji} **{vuln.get('package_name', 'Unknown package')} ({vuln.get('package_version', 'Unknown version')})**
  * CVE: {vuln.get('CVE', 'No CVE')}
  * Severity: {severity}
  * CVSS Score: {vuln.get('cvss_score', 'N/A')}
  * Advisory: {vuln.get('advisory', 'Not available')}
""")

            if remediations:
                report_sections.append("\n### Remediations\n")
                for rem in remediations:
                    report_sections.append(f"""
📝 **{rem.get('package_name', 'Unknown package')}**
  * Current version: {rem.get('current_version', 'Unknown')}
  * Recommended version: {rem.get('recommended_version', 'Unknown')}
  * Note: {rem.get('note', 'No additional information')}
""")

    # Join all sections and return the complete report
    return "".join(report_sections)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python security_scan.py <directory>")
        sys.exit(1)

    directory = sys.argv[1]
    print(generate_markdown_report(directory))
