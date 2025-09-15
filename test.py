import sys

from PyPDF2 import PdfReader
from Gpt import Gpt
from settings import DEFAULT_GPT_MODEL,MARKDOWN_PROMPT
from utils import evaluate_query
import re
from pathlib import Path


def starts_with_number(s):
    return bool(re.match(r"^\d+", s))


def ends_with_dots_number(s):
    return bool(re.search(r"\.\s*\d+$", s))


def get_cis_recommendation_mappings(pdf_filename, toc_start, toc_end, rec_grouping, query_params):
    reader = PdfReader(pdf_filename)
    table_of_contents = ""

    # Extract the whole TOC
    for page in reader.pages[toc_start:toc_end]:
        table_of_contents += page.extract_text()

    active_section = ""
    sections = []
    current_section = {"start": "", "end": "", "name": ""}
    looking_for_start = True
    looking_for_end = False
    for line in table_of_contents.split("\n"):
        line = line.strip()
        if starts_with_number(line):
            section = line.split(" ")[0]
            if section.startswith(active_section) or active_section == "":
                # Either section contains L1/L2 directly
                #if '(L1)' in line or "(L2)" in line or "(Manually)" in line or "(Automated)" in line:
                if evaluate_query(line, query_params):
                    current_section["name"] = active_section
                else:
                    # Or we have entered a new subsection
                    if rec_grouping == "Outermost":
                        if "." not in section:
                            active_section = section
                            looking_for_start = True
                    else:
                        active_section = section
                        looking_for_start = True
            else:
                # We are at next section
                # Close current-section
                looking_for_end = True
                active_section = section
        if looking_for_start:
            if ends_with_dots_number(line.strip()):
                current_section["start"] = line.split(". ")[-1].strip().replace(".", "").replace(".", "")
                looking_for_start = False
        if looking_for_end:
            if ends_with_dots_number(line.strip()):
                end = line.split(".. ")[-1].strip().replace(".", "").replace(".", "")
                current_section["end"] = end
                if current_section["name"]:
                    sections.append(current_section)
                looking_for_end = False
                current_section = {"start": end, "end": "", "name": ""}
        if "appendix:" in line.lower():
            # We are at end, at end to active section if not exists
            if current_section["start"] and current_section["name"] and not current_section["end"]:
                current_section["end"] = line.split(". ")[-1].strip().replace(".", "").replace(".", "")

    if not current_section in sections:
        sections.append(current_section)

    for section in sections:
        section_text = ""
        start_index = int(section["start"])
        if not section["end"]:
            section["end"] = start_index + 2
        end_index = int(section["end"])
        for page in reader.pages[start_index:end_index]:
            section_text += page.extract_text()
        section["content"] = section_text

    return [section for section in sections if section["name"]]



def get_markdown_from_cis_section(gpt_key, output_folder, section):
    gpt = Gpt(gpt_key, MARKDOWN_PROMPT)

    markdown = gpt.answer_prompt("Section: {} \n Recommendations: {}".format(section["name"], section["content"]))
    with open(f"{output_folder}/{section['name']}.md", 'w') as f:
        clean_markdown = str(markdown.content).replace("```markdown", "").replace("```", "")
        f.write(clean_markdown)

    return f"{output_folder}/{section['name']}.md"


if __name__ == '__main__':
    get_cis_recommendation_mappings("doc.pdf", 2, 25, "Outermost", [{"op": "initial", "text": "L1"}, {"op": "or", "text": "L2"}])
