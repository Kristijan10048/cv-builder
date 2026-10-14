"""Extract explicit spoken-language requirements without inferring from job location."""

from abc import ABC, abstractmethod
import re

from bs4 import BeautifulSoup

C_EMPTY_TEXT = ""
C_TEXT_SEPARATOR = " "
C_PATTERN_SEPARATOR = "|"
C_HTML_PARSER = "html.parser"
C_LANGUAGE_ALIASES = {
    "English": r"english|englisch|engels",
    "German": r"german|deutsch|duits",
    "Dutch": r"dutch|nederlands|niederländisch",
    "French": r"french|français|französisch|frans",
    "Spanish": r"spanish|español|spanisch|spaans",
    "Italian": r"italian|italiano|italienisch|italiaans",
    "Portuguese": r"portuguese|português|portugiesisch|portugees",
    "Polish": r"polish|polski|polnisch|pools",
    "Swedish": r"swedish|svenska|schwedisch|zweeds",
    "Danish": r"danish|dansk|dänisch|deens",
    "Norwegian": r"norwegian|norsk|norwegisch|noors",
    "Finnish": r"finnish|suomi|finnisch|fins",
    "Czech": r"czech|čeština|tschechisch|tsjechisch",
    "Romanian": r"romanian|română|rumänisch|roemeens",
    "Hungarian": r"hungarian|magyar|ungarisch|hongaars",
    "Greek": r"greek|griechisch|grieks",
    "Turkish": r"turkish|türkçe|türkisch|turks",
    "Arabic": r"arabic|arabisch",
    "Chinese": r"chinese|mandarin|chinesisch|mandarijn",
    "Japanese": r"japanese|japanisch|japans",
    "Korean": r"korean|koreanisch|koreaans",
    "Hindi": r"hindi",
    "Russian": r"russian|russisch",
    "Ukrainian": r"ukrainian|ukrainisch|oekraïens",
}
C_LANGUAGE_ALTERNATIVES = C_PATTERN_SEPARATOR.join(C_LANGUAGE_ALIASES.values())
C_LANGUAGE_NAME = rf"\b(?:{C_LANGUAGE_ALTERNATIVES})(?:kenntnisse[n]?)?\b"
C_LANGUAGE_LEVEL = r"[ABC][12](?:\s*[-–/]\s*[ABC][12])?"
C_LANGUAGE_ENTRY = rf"{C_LANGUAGE_NAME}(?:\s*\({C_LANGUAGE_LEVEL}\))?"
C_LANGUAGE_LIST = (
    rf"{C_LANGUAGE_ENTRY}(?:\s*(?:,|/|&|and/or|and|or|und|oder|en|of)\s*"
    rf"{C_LANGUAGE_ENTRY})*"
)
C_PROFICIENCY = (
    r"fluent|fluency|proficient|proficiency|native|bilingual|business[- ]level|"
    r"professional|excellent|strong|good|working|advanced|"
    r"fließend(?:e[nr]?)?|fliessend(?:e[nr]?)?|verhandlungssicher(?:e[nr]?)?|"
    r"sehr\s+gute[nr]?|gute[nr]?|vloeiend|uitstekend|goede?"
)
C_LANGUAGE_QUALIFIERS = (
    r"(?:(?:written|spoken|oral|verbal|communication|language|skills|knowledge|command|and|in|of|"
    r"kenntnisse|kenntnissen|in\s+wort\s+und\s+schrift)\s+)*"
)
C_REQUIRED = (
    r"required|mandatory|essential|necessary|a\s+must|"
    r"erforderlich|vorausgesetzt|zwingend|verplicht|vereist"
)
C_REQUIREMENT_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    rf"\b(?:{C_PROFICIENCY})\s+{C_LANGUAGE_QUALIFIERS}{C_LANGUAGE_LIST}",
    rf"\b(?:knowledge|command|proficiency|fluency)\s+(?:of|in)\s+{C_LANGUAGE_LIST}",
    rf"\b(?:must|need\s+to|required\s+to)\s+(?:be\s+able\s+to\s+)?"
    rf"(?:speak|write|communicate\s+in)\s+{C_LANGUAGE_LIST}",
    rf"\b(?:must|need\s+to|required\s+to)\s+(?:have|possess)\s+"
    rf"(?:(?:{C_PROFICIENCY})\s+)?{C_LANGUAGE_QUALIFIERS}{C_LANGUAGE_LIST}",
    rf"{C_LANGUAGE_LIST}\s+(?:(?:language|communication)\s+)?"
    rf"(?:(?:skills|knowledge|proficiency|fluency)\s*)?"
    rf"(?:(?:is|are|ist|sind|niveau|level|at|at\s+least)\s+)*(?::\s*)?"
    rf"(?:{C_REQUIRED}|{C_LANGUAGE_LEVEL}\b|{C_PROFICIENCY}\b)",
    rf"\b(?:{C_LANGUAGE_LEVEL})\s+(?:(?:level|in)\s+)*{C_LANGUAGE_LIST}",
))
C_LANGUAGE_PATTERN = re.compile(C_LANGUAGE_NAME, re.IGNORECASE)
C_KNOWLEDGE_SUFFIX_PATTERN = re.compile(r"kenntnisse[n]?$", re.IGNORECASE)
C_ALIAS_PATTERNS = tuple(
    (language_name, re.compile(rf"(?:{aliases})", re.IGNORECASE))
    for language_name, aliases in C_LANGUAGE_ALIASES.items()
)
C_BLOCK_TAG_PATTERN = re.compile(r"</?(?:p|li|div|br|h[1-6])\b[^>]*>", re.IGNORECASE)
C_CLAUSE_PATTERN = re.compile(
    r"[.!?;\n]+|\b(?:but|however|whereas|while|aber|jedoch|maar)\b|"
    rf"(?:,|\b(?:and|und|en)\b)\s*(?=(?:(?:no|kein|geen)\s+{C_LANGUAGE_NAME}|"
    rf"{C_LANGUAGE_NAME}\s+(?:(?:is|are|ist|sind)\s+)?"
    r"(?:not|optional|preferred|desirable|a\s+plus)))",
    re.IGNORECASE,
)
C_OPTIONAL_OR_NEGATED_PATTERN = re.compile(
    r"\b(?:not|no|without|optional|preferred|preferably|desirable|advantage|"
    r"nice[- ]to[- ]have|a\s+plus|bonus|not\s+necessary|"
    r"nicht|kein(?:e[nr]?)?|ohne|wünschenswert|von\s+vorteil|"
    r"pluspunt|pré|pre|geen|niet)\b",
    re.IGNORECASE,
)
C_HIDDEN_HTML_ELEMENTS = ("script", "style")
C_LINE_BREAK = "\n"
C_MARKDOWN_FORMATTING_PATTERN = re.compile(r"[*_`]+")


class LanguageRequirementExtractor(ABC):
    """Define a replaceable parser interface for a future local language model."""

    @abstractmethod
    def extract(self, description: str | None) -> list[str]:
        """Return distinct languages explicitly required by a job description."""


class RegexLanguageRequirementExtractor(LanguageRequirementExtractor):
    """Recognize common requirement phrases in English, German, and Dutch text."""

    @staticmethod
    def description_text(description: str | None) -> str:
        """Preserve paragraph boundaries while removing HTML and hidden content."""
        if not description:
            return C_EMPTY_TEXT
        separated_description = C_BLOCK_TAG_PATTERN.sub(C_LINE_BREAK, description)
        document = BeautifulSoup(separated_description, C_HTML_PARSER)
        for hidden_element in document.find_all(C_HIDDEN_HTML_ELEMENTS):
            hidden_element.decompose()
        return C_MARKDOWN_FORMATTING_PATTERN.sub(
            C_EMPTY_TEXT, document.get_text(C_TEXT_SEPARATOR),
        )

    def extract(self, description: str | None) -> list[str]:
        """Ignore incidental, optional, and negated mentions; retain first-match order."""
        required_languages = []
        description_text = self.description_text(description)
        for clause in C_CLAUSE_PATTERN.split(description_text):
            # Conservative clause filtering avoids treating preferences as requirements.
            if C_OPTIONAL_OR_NEGATED_PATTERN.search(clause):
                continue
            requirement_matches = sorted(
                (
                    requirement_match
                    for requirement_pattern in C_REQUIREMENT_PATTERNS
                    for requirement_match in requirement_pattern.finditer(clause)
                ),
                key=lambda requirement_match: requirement_match.start(),
            )
            for requirement_match in requirement_matches:
                for language_match in C_LANGUAGE_PATTERN.finditer(requirement_match.group()):
                    language_alias = C_KNOWLEDGE_SUFFIX_PATTERN.sub(
                        C_EMPTY_TEXT, language_match.group(),
                    )
                    for language_name, alias_pattern in C_ALIAS_PATTERNS:
                        if alias_pattern.fullmatch(language_alias):
                            if language_name not in required_languages:
                                required_languages.append(language_name)
                            break
        return required_languages
