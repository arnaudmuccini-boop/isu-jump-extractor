import re
from io import BytesIO
import pdfplumber
import requests

# ---------------------------------------------------------------------------
# Season 2026-2027 Schedule & Event Directory Slugs
# ---------------------------------------------------------------------------
SEASON_EVENTS = [
    {"name": "ISU JGP Xi'An 2026", "slug": "jgpchn2026"},
    {"name": "ISU JGP Riga 2026", "slug": "jgplat2026"},
    {"name": "ISU JGP Bangkok 2026", "slug": "jgptha2026"},
    {"name": "ISU JGP Ankara 2026", "slug": "jgptur2026"},
    {"name": "ISU JGP Batumi 2026", "slug": "jgpgeo2026"},
    {"name": "ISU JGP Ljubljana 2026", "slug": "jgpslo2026"},
    {"name": "ISU JGP Gdansk 2026", "slug": "jgppol2026"},
    {"name": "ISU Grand Prix de France 2026", "slug": "gpfra2026"},
    {"name": "ISU Skate Canada International 2026", "slug": "gpcan2026"},
    {"name": "ISU Cup of China 2026", "slug": "gpchn2026"},
    {"name": "ISU Skate America 2026", "slug": "gpcusa2026"},
    {"name": "ISU Finlandia Trophy 2026", "slug": "gpfin2026"},
    {"name": "ISU NHK Trophy 2026", "slug": "gpjpn2026"},
    {"name": "ISU Grand Prix Final 2026", "slug": "gpf2026"},
    {"name": "ISU European Championships 2027", "slug": "ec2027"},
    {"name": "ISU Four Continents Championships 2027", "slug": "fc2027"},
    {"name": "ISU World Junior Championships 2027", "slug": "wjc2027"},
    {"name": "ISU World Championships 2027", "slug": "wc2027"},
    {"name": "ISU World Team Trophy 2027", "slug": "wtt2027"},
]

BASE_URL = "https://results.isu.org/results/season2627/"

# Technical Exclusions & Jump Recognition Patterns
FORBIDDEN_FLAGS = {"!", "e", "<", "<<", "q", "*", "REP", "COMBO", "FALL"}
JUMP_PATTERN = re.compile(
    r"\b\d[T|S|Lo|F|Lz|A]\b|\b\d[A-Za-z]+\+\d[A-Za-z]+"
)


def calculate_trimmed_mean(scores):
    """Sorts 9 judge scores, drops highest and lowest, averages middle 7."""
    if len(scores) < 9:
        return None
    sorted_scores = sorted(scores[:9])
    trimmed = sorted_scores[1:8]
    return round(sum(trimmed) / 7.0, 2)


def process_protocol_pdf(pdf_bytes):
    """Parses an ISU protocol PDF and extracts jump elements meeting criteria."""
    detailed_breakdown = []
    qualified_summary = []

    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""

                # Extract Skater Name and Nation
                skater_match = re.search(
                    r"(\d+)\s+([A-Za-z\s\'-]+)\s+([A-Z]{3})", text
                )
                if not skater_match:
                    continue

                rank, skater_name, nation = skater_match.groups()
                skater_header = f"{skater_name.strip()} ({nation.strip()})"

                skater_detailed = [f"{rank} {skater_header}"]
                skater_qualified = []

                tables = page.extract_tables()
                element_order = 0

                for table in tables:
                    for row in table:
                        if not row or len(row) < 10:
                            continue

                        element_name = str(row[1]).strip() if row[1] else ""
                        info_flag = str(row[2]).strip() if row[2] else ""

                        # Target Jump Elements
                        if JUMP_PATTERN.search(element_name) or any(
                            j in element_name
                            for j in ["T", "S", "Lo", "F", "Lz", "A"]
                        ):
                            element_order += 1
                            has_flag = any(
                                flag in info_flag for flag in FORBIDDEN_FLAGS
                            )

                            # Parse 9 Judge Scores
                            try:
                                judge_scores = [
                                    int(x)
                                    for x in row[4:13]
                                    if x and x.replace("-", "").isdigit()
                                ]
                            except ValueError:
                                continue

                            if len(judge_scores) == 9:
                                trimmed_mean = calculate_trimmed_mean(
                                    judge_scores
                                )

                                if has_flag:
                                    skater_detailed.append(
                                        f"{element_name}: Flag detected ({info_flag}). Disqualified."
                                    )
                                elif (
                                    trimmed_mean is not None
                                    and trimmed_mean >= 2.50
                                ):
                                    skater_detailed.append(
                                        f"{element_name}: Raw GOE panel: {judge_scores} "
                                        f"(Trimmed Mean = {trimmed_mean:.2f}) -> Average GOE+3 (Qualified)"
                                    )
                                    skater_qualified.append(
                                        f"{element_order} {element_name}: Average GOE+3: +{trimmed_mean:.2f}"
                                    )
                                else:
                                    skater_detailed.append(
                                        f"{element_name}: Trimmed mean is below +2.50 threshold ({trimmed_mean}). Disqualified."
                                    )

                if len(skater_detailed) > 1:
                    detailed_breakdown.extend(skater_detailed)
                if skater_qualified:
                    qualified_summary.append(skater_header)
                    qualified_summary.extend(skater_qualified)

    except Exception as e:
        print(f"Error parsing PDF: {e}")

    return detailed_breakdown, qualified_summary


def run_extraction():
    full_report = []

    # Segment PDF naming conventions for Men & Women (Junior/Senior)
    segments = [
        "FSKMSINGLES-JUNIOR----QUAL000100--_JudgesDetailsperSkater.pdf",
        "FSKMSINGLES-JUNIOR----FNL-000100--_JudgesDetailsperSkater.pdf",
        "FSKWSINGLES-JUNIOR----QUAL000100--_JudgesDetailsperSkater.pdf",
        "FSKWSINGLES-JUNIOR----FNL-000100--_JudgesDetailsperSkater.pdf",
        "FSKMSINGLES-SENIOR----QUAL000100--_JudgesDetailsperSkater.pdf",
        "FSKMSINGLES-SENIOR----FNL-000100--_JudgesDetailsperSkater.pdf",
        "FSKWSINGLES-SENIOR----QUAL000100--_JudgesDetailsperSkater.pdf",
        "FSKWSINGLES-SENIOR----FNL-000100--_JudgesDetailsperSkater.pdf",
    ]

    for event in SEASON_EVENTS:
        event_url = f"{BASE_URL}{event['slug']}/"

        for segment_pdf in segments:
            pdf_url = f"{event_url}{segment_pdf}"

            try:
                res = requests.get(pdf_url, timeout=5)
                if res.status_code == 200:
                    detailed, summary = process_protocol_pdf(res.content)

                    if detailed or summary:
                        full_report.append(f"=== EVENT: {event['name']} ===")
                        full_report.append("\nDetailed Breakdown")
                        full_report.extend(detailed)
                        full_report.append("\nQualified Jump Elements Summary")
                        full_report.extend(summary)
                        full_report.append("\n" + "=" * 50 + "\n")
            except Exception:
                continue

    output_content = (
        "\n".join(full_report)
        if full_report
        else "No new qualifying jumps found for this period."
    )

    with open("output_report.txt", "w", encoding="utf-8") as f:
        f.write(output_content)

    print(output_content)


if __name__ == "__main__":
    run_extraction()
