"""
Suburb Matcher Service
Fuzzy matching for South Australian suburb names in SAAS job locations
"""

from typing import Optional, Tuple
from rapidfuzz import fuzz, process

from app.data.sa_suburbs import SA_SUBURBS, SA_SUBURB_ALIASES


class SuburbMatcher:
    """Fuzzy matcher for SA suburb names using rapidfuzz"""

    def __init__(self, min_score: int = 80):
        """
        Initialize the suburb matcher.

        Args:
            min_score: Minimum fuzzy match score (0-100) required for a match.
                       80 is recommended for good balance between catching typos
                       and avoiding false matches.
        """
        self.min_score = min_score
        self.suburbs = SA_SUBURBS
        self.aliases = SA_SUBURB_ALIASES

    def match(self, text: str) -> Optional[Tuple[str, int]]:
        """
        Match text to a SA suburb using fuzzy logic.

        Args:
            text: The suburb text to match (e.g., "ADELAIE", "PT AUGUSTA")

        Returns:
            Tuple of (matched_suburb, confidence_score) or None if no match found
        """
        if not text or not text.strip():
            return None

        text = text.upper().strip()

        # First, check exact match
        if text in self.suburbs:
            return (text, 100)

        # Second, check aliases for common abbreviations/typos
        if text in self.aliases:
            return (self.aliases[text], 100)

        # Third, use fuzzy matching against suburb list
        result = process.extractOne(
            text,
            self.suburbs,
            scorer=fuzz.ratio,
            score_cutoff=self.min_score
        )

        if result:
            matched_suburb, score, _ = result
            return (matched_suburb, int(score))

        # Fourth, try token_sort_ratio for multi-word suburbs that might be reordered
        # e.g., "AUGUSTA PORT" -> "PORT AUGUSTA"
        result = process.extractOne(
            text,
            self.suburbs,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=self.min_score
        )

        if result:
            matched_suburb, score, _ = result
            return (matched_suburb, int(score))

        return None

    def normalize(self, text: str) -> str:
        """
        Normalize suburb text - apply alias corrections and fuzzy matching.

        Args:
            text: The suburb text to normalize

        Returns:
            The normalized/corrected suburb name, or original if no match
        """
        if not text or not text.strip():
            return text

        text = text.upper().strip()

        # Apply alias corrections first (these are exact matches)
        if text in self.aliases:
            return self.aliases[text]

        # Try fuzzy match
        match_result = self.match(text)
        if match_result:
            matched_suburb, score = match_result
            return matched_suburb

        # Return original if no match found
        return text

    def is_valid_suburb(self, text: str) -> bool:
        """
        Check if text is a valid SA suburb (exact or fuzzy match).

        Args:
            text: The text to validate

        Returns:
            True if text matches a known SA suburb
        """
        return self.match(text) is not None

    def get_match_confidence(self, text: str) -> int:
        """
        Get the confidence score for a suburb match.

        Args:
            text: The suburb text to check

        Returns:
            Confidence score 0-100, or 0 if no match
        """
        result = self.match(text)
        return result[1] if result else 0

    def extract_suburb_from_text(self, text: str) -> Optional[str]:
        """
        Extract a suburb name from text by scanning for known SA suburbs.
        Handles text with prefixes, codes, and other noise.

        This method looks for suburb names (including multi-word suburbs)
        within the text and returns the best match.

        Args:
            text: The text to search for suburbs (e.g., ": H715 SALISBURY EAST 71 M 9")

        Returns:
            The matched suburb name, or None if no match found
        """
        if not text or not text.strip():
            return None

        text = text.upper().strip()

        # Build list of potential suburb candidates by looking for
        # consecutive uppercase word sequences
        words = text.split()

        # Try progressively smaller word combinations (longest first)
        # to catch multi-word suburbs like "PORT AUGUSTA" or "SALISBURY EAST"
        best_match = None
        best_score = 0

        for window_size in range(min(4, len(words)), 0, -1):
            for i in range(len(words) - window_size + 1):
                candidate_words = words[i:i + window_size]

                # Skip if any word looks like a code/number pattern
                # but allow words that are part of suburb names
                skip = False
                for word in candidate_words:
                    # Skip pure numbers, alphanumeric codes, or special prefixes
                    if (word.isdigit() or
                        word.startswith('@') or
                        word.startswith('?') or
                        word == 'CB' or
                        word == 'PR:' or
                        word == 'Disp:' or
                        (len(word) <= 4 and any(c.isdigit() for c in word) and word not in self.suburbs)):
                        skip = True
                        break
                if skip:
                    continue

                candidate = ' '.join(candidate_words)

                # Check for exact match first
                if candidate in self.suburbs:
                    return candidate

                # Check aliases
                if candidate in self.aliases:
                    return self.aliases[candidate]

                # Try fuzzy match
                result = self.match(candidate)
                if result:
                    matched_suburb, score = result
                    # Prefer longer matches and higher scores
                    adjusted_score = score + (window_size * 5)
                    if adjusted_score > best_score:
                        best_score = adjusted_score
                        best_match = matched_suburb

        return best_match


# Singleton instance for use across the application
_suburb_matcher: Optional[SuburbMatcher] = None


def get_suburb_matcher() -> SuburbMatcher:
    """Get the singleton SuburbMatcher instance"""
    global _suburb_matcher
    if _suburb_matcher is None:
        _suburb_matcher = SuburbMatcher(min_score=80)
    return _suburb_matcher
