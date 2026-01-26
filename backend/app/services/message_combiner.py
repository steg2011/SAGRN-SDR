"""
Multi-part message combiner for SAGRN pager messages.

Some pager messages are split across multiple transmissions due to length limits.
This module combines them before parsing.

Pattern:
- Part 1: Message content ending with "(Part 1 of 2)"
- Part 2: Continuation ending with ":(Part 2 of 2)"
- Both share the same capcode in the FLEX header
"""

import re
import time
from dataclasses import dataclass
from typing import Optional, Dict, Tuple


@dataclass
class BufferedPart:
    """A buffered Part 1 message waiting for Part 2"""
    raw_message: str
    content_before_marker: str
    capcode: str
    timestamp: float  # time.time() when received
    flex_prefix: str  # The FLEX header to preserve


class MessageCombiner:
    """
    Combines multi-part pager messages.

    Buffers Part 1 messages and combines them when Part 2 arrives.
    """

    # Pattern to match Part 1 marker - "(Part 1 of 2)"
    PART1_PATTERN = re.compile(r'\(Part 1 of (\d+)\)\s*$')

    # Pattern to match Part 2 marker - ":(Part 2 of 2)"
    PART2_PATTERN = re.compile(r':\(Part 2 of (\d+)\)\s*$')

    # Pattern to extract capcode from FLEX message
    # Format: FLEX|timestamp|speed|frame|capcode|type|content
    FLEX_CAPCODE_PATTERN = re.compile(
        r'^(FLEX\|[^|]+\|[^|]+\|[^|]+\|)(\d+)(\|[^|]+\|)(.+)$'
    )

    # How long to keep Part 1 messages in buffer (seconds)
    BUFFER_TIMEOUT = 60

    def __init__(self):
        # Buffer for Part 1 messages, keyed by capcode
        self._buffer: Dict[str, BufferedPart] = {}

    def process(self, raw_message: str) -> Tuple[Optional[str], bool]:
        """
        Process a raw message, potentially combining multi-part messages.

        Args:
            raw_message: The raw FLEX message line

        Returns:
            Tuple of (processed_message, was_combined)
            - If this is Part 1: returns (None, False) - buffered for later
            - If this is Part 2 with matching Part 1: returns (combined_message, True)
            - If this is a normal message: returns (raw_message, False)
        """
        # Clean expired entries
        self._clean_expired()

        # Extract capcode and content from FLEX format
        flex_match = self.FLEX_CAPCODE_PATTERN.match(raw_message)
        if not flex_match:
            # Not a FLEX message, return as-is
            return raw_message, False

        flex_prefix = flex_match.group(1)  # FLEX|timestamp|speed|frame|
        capcode = flex_match.group(2)
        flex_suffix = flex_match.group(3)  # |type|
        content = flex_match.group(4)

        # Check if this is Part 2
        part2_match = self.PART2_PATTERN.search(content)
        if part2_match:
            return self._handle_part2(raw_message, capcode, content, part2_match)

        # Check if this is Part 1
        part1_match = self.PART1_PATTERN.search(content)
        if part1_match:
            return self._handle_part1(raw_message, capcode, content, part1_match,
                                     flex_prefix, flex_suffix)

        # Normal message, return as-is
        return raw_message, False

    def _handle_part1(self, raw_message: str, capcode: str, content: str,
                      match: re.Match, flex_prefix: str, flex_suffix: str) -> Tuple[None, bool]:
        """Buffer a Part 1 message for later combination."""
        # Extract the content before the Part marker
        content_before = content[:match.start()]

        # Store in buffer
        self._buffer[capcode] = BufferedPart(
            raw_message=raw_message,
            content_before_marker=content_before,
            capcode=capcode,
            timestamp=time.time(),
            flex_prefix=flex_prefix + capcode + flex_suffix
        )

        # Return None to indicate this message should be held
        return None, False

    def _handle_part2(self, raw_message: str, capcode: str, content: str,
                      match: re.Match) -> Tuple[Optional[str], bool]:
        """
        Combine Part 2 with buffered Part 1.

        Returns combined message if Part 1 exists, otherwise returns Part 2 alone.
        """
        # Extract Part 2 content (before the marker)
        # The marker is ":(Part 2 of 2)" so content before it is the units
        part2_content = content[:match.start()]

        # Look for matching Part 1 in buffer
        buffered = self._buffer.pop(capcode, None)

        if buffered:
            # Combine: Part 1 content + Part 2 content + trailing colon
            # Remove trailing space from Part 1 content if present
            part1_content = buffered.content_before_marker.rstrip()

            # Add space between parts if needed
            if part1_content and part2_content and not part2_content.startswith(' '):
                combined_content = part1_content + ' ' + part2_content.rstrip()
            else:
                combined_content = part1_content + part2_content.rstrip()

            # Add trailing colon to match expected format ":UNITS :"
            # This is needed for the parser to extract units correctly
            if not combined_content.endswith(':'):
                combined_content = combined_content + ' :'

            # Reconstruct the full FLEX message
            combined_message = buffered.flex_prefix + combined_content

            return combined_message, True

        # No matching Part 1 found - return as-is (might have expired or arrived out of order)
        return raw_message, False

    def _clean_expired(self):
        """Remove expired Part 1 messages from buffer."""
        current_time = time.time()
        expired = [
            capcode for capcode, part in self._buffer.items()
            if current_time - part.timestamp > self.BUFFER_TIMEOUT
        ]
        for capcode in expired:
            del self._buffer[capcode]

    def get_pending_count(self) -> int:
        """Get count of buffered Part 1 messages awaiting Part 2."""
        return len(self._buffer)

    def flush_pending(self) -> list:
        """
        Flush all pending Part 1 messages that haven't received Part 2.
        Returns list of the buffered raw messages.
        """
        messages = [part.raw_message for part in self._buffer.values()]
        self._buffer.clear()
        return messages


# Global instance for use across the application
_combiner: Optional[MessageCombiner] = None


def get_message_combiner() -> MessageCombiner:
    """Get the global MessageCombiner instance."""
    global _combiner
    if _combiner is None:
        _combiner = MessageCombiner()
    return _combiner
